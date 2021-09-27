from http import HTTPStatus
import queue
import socket
import os
import time
import sys
import selectors
from ipaddress import ip_network
from http.server import BaseHTTPRequestHandler
from types import SimpleNamespace
from typing import Tuple, Dict, Union, List, Optional
from types import SimpleNamespace
from io import BytesIO
from Device import Device
from SSS3Handle import SSS3Handle
from ClientHandle import ClientHandle
import logging
from logging.handlers import TimedRotatingFileHandler
from HelperMethods import ColoredConsoleHandler, LogFolder
import http.client

"""TODO Notes:
    - We need to set the keep alive function on the teensy.
    - When recving or sending timeout should be calculated dynamically.
        - From:
          https://www.geeksforgeeks.org/algorithm-for-dynamic-time-out-timer-calculation/
            - Use Karn's Modification with Jacob's Algorithm to dynamically
              calculate timeout and when to retransmit.
"""

# Type Aliases
SOCKTYPE = socket.socket
SEL = selectors.SelectorKey

class Broker(BaseHTTPRequestHandler):

    # ==================== Initialization ====================

    def __init__(self) -> None:
        self.__setup_logging()
        self.log_message("Broker Initializing.")
        self.protocol_version = "HTTP/1.1"
        self.sel = selectors.DefaultSelector()
        self.multicast_IPs = []
        for ip in ip_network('239.255.0.0/16'):
            self.multicast_IPs.append({
                "ip": ip,
                "available": True,
                "sockets": []
            })
        self.blacklist_ips = []
        self.SSS3s = SSS3Handle(self.sel, self.multicast_IPs)
        self.CLIENTs = ClientHandle(self.sel, self.multicast_IPs)

    def __setup_logging(self):
        filename = LogFolder.findpath("broker_log")
        logging.basicConfig(
            format='%(asctime)s - %(filename)s - %(levelname)s - %(message)s',
            level=logging.DEBUG,
            handlers=[
                TimedRotatingFileHandler(
                    filename=filename,
                    when="midnight",
                    interval=1,
                    backupCount=7,
                    encoding='utf-8'
                    ),
                ColoredConsoleHandler()
                ]
            )
        # self.logger = logging.getLogger(__name__)
        # self.logger.setLevel(logging.DEBUG)

    # ===== Overrides for parent class functions =====

    def log_error(self, format, *args):
        address_string = "SERVER"
        if hasattr(self, "client_address"):
            address_string = self.client_address[0]
        logging.error("%s - - %s\n" %
                         (address_string, format%args))

    def log_message(self, format, *args):
        address_string = "SERVER"
        if hasattr(self, "client_address"):
            address_string = self.client_address[0]
        logging.info("%s - - %s\n" %
                         (address_string, format%args))

    def end_headers(self):
        """Send the blank line ending the MIME headers."""
        self.wfile.seek(0)
        message_body = self.wfile.read()
        self.wfile.seek(0)
        message_body_len = len(message_body)
        self.send_header("Content-Length", str(message_body_len))
        if message_body_len > 0:
            self.send_header("Content-Type", "application/json")
        if not self.close_connection:
                self.send_header("Connection", "keep-alive")
        if self.request_version != 'HTTP/0.9':
            self._headers_buffer.append(b"\r\n")
            self.flush_headers(message_body)

    def flush_headers(self, message_body=b""):
        if hasattr(self, '_headers_buffer'):
            headers = b"".join(self._headers_buffer)
            self.wfile.write(headers)
            self.wfile.write(message_body)
            self._headers_buffer = []

    # ==================== Main Server Functions ====================

    def listen(self):
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        device_address = socket.gethostbyname_ex(socket.gethostname())[2][3]
        lsock.bind((device_address, 80))
        # lsock.bind(("127.0.0.1", 80))
        lsock.listen()
        lsock.setblocking(False)
        data = SimpleNamespace(callback=self.__accept)
        self.sel.register(lsock, selectors.EVENT_READ, data=data)
        self.log_message(f'Listening on: {device_address}:80')
        self.__handle_connection()

    def __handle_connection(self) -> None:
        while True:
            try:
                connection_events = self.sel.select(timeout=1)
            except TimeoutError:
                continue
            except KeyboardInterrupt:
                return
            else:
                for key, mask in connection_events:
                    self.__handle_mask_events(key, mask)
                self.__prune_connections()

    def __handle_mask_events(self, key: SEL, mask):
        if mask == selectors.EVENT_READ:
            if key.data.callback == self.__accept:
                callback = key.data.callback
                callback(key)
            elif not key.data.rate_limit:
                time.sleep(0.001)  # Small hack to let the rest of the message
                                    # make it in to the socket before reading it.
                self.__call_callback(key)
        else:
            self.__call_callback(key)

    def __call_callback(self, key: SEL):
        with key.data.addr as self.client_address:
            callback = key.data.callback
            callback(key)

    def __prune_connections(self) -> None:
        """Loose connections are accepted connections from devices that don't
        register within 5 seconds of connecting."""
        current_time = time.time()
        for fd, key in self.sel.get_map():
            try:
                if key.data.is_loose(current_time, self.log_error):
                    self.__shutdown_connection(key)
            except AttributeError:
                continue

    def __accept(self, key: SEL) -> None:
        """Takes a new connection from the listening socket and assigns it its
        own socket. Then registers it with the selectors using the READ mask.
        """
        conn, addr = key.fileobj.accept()
        conn.setblocking(False)
        if addr[0] in self.blacklist_ips:
            self.log_error(f'Blacklisted IP address: {addr[0]} tried to connect.')
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
        else:
            self.log_message(f'New connection from: {addr[0]}:{str(addr[1])}')
            self.__set_keepalive(conn, 300000, 300000)
            data = Device(self.__read, self.__write, addr)
            self.sel.register(conn, selectors.EVENT_READ, data=data)

    def __set_keepalive(self, conn: SOCKTYPE, idle_sec: int, interval_sec: int) -> None:
        if os.name == 'nt':
            conn.ioctl(socket.SIO_KEEPALIVE_VALS, (1, idle_sec, interval_sec))
        else:
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle_sec)
            conn.setsockopt(socket.IPPROTO_TCP,
                            socket.TCP_KEEPINTVL, interval_sec)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 10)

    def __read(self, key: SEL):
        if key.data.expecting_response:
            self.__handle_response(key)
        else:
            try:
                message = self._key.fileobj.recv(4096)
                self.__handle_request(key, message)
            except OSError as ose:
                key.data.close_connection = True
                self.__shutdown_connection(key)
                self.log_error(ose)

    def __handle_request(self, key: SEL, message: bytes) -> None:
        with BytesIO() as self.wfile, BytesIO(message) as self.rfile:
            self.handle_one_request()
            if len(self.wfile) > 0:
                self.end_headers()
                self.wfile.seek(0)
                key.data.outgoing_messages.put(self.wfile.read())
                key.data.callback = self.__write
                key.data.close_connection = self.close_connection
                self.sel.modify(key.fileobj, selectors.EVENT_WRITE, key.data)
            else:
                logging.info(f'{key.data.addr[0]} - - Closed the connection.')
                self.__shutdown_connection(key)

    def __handle_response(self, key: SEL):
        key.data.response = http.client.HTTPResponse(key.fileobj)
        try:
            key.data.response.begin()
            key.data.expecting_response = False
        except http.client.HTTPException as he:
            self.log_error(he)
            key.data.close_connection = True
            self.__shutdown_connection(key)

    def do_GET(self):
        self.__method_poxy()

    def do_HEAD(self):
        self.__method_poxy()

    def do_POST(self):
        self.__method_poxy()

    def do_PUT(self):
        self.__method_poxy()

    def do_DELETE(self):
        self.__method_poxy()

    def do_OPTIONS(self):
        self.__method_poxy()

    def do_CONNECT(self):
        self.__method_poxy()

    def do_TRACE(self):
        self.__method_poxy()

    def __method_poxy(self):
        list_name, method_name = self.__parse_path()
        try:
            device_list = getattr(self, list_name)
        except AttributeError as ae:
            logging.debug(ae)
            self.log_error("Requested a non-existent device type.")
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            method_handle = getattr(device_list, method_name)
            response = method_handle(self._key, self.rfile, self.wfile)
            if response == HTTPStatus.FORBIDDEN:
                self.blacklist_ips.append(self._key.addr[0])
                self._key.data.close_connection = True
            self.send_response(response)
        except AttributeError as ae:
            logging.debug(ae)
            self.log_error("Requested a method that is not implemented.")
            self.send_error(HTTPStatus.NOT_IMPLEMENTED)

    def __parse_path(self):
        second_slash = self.path.find('/', 1)
        if second_slash == -1:
            list_name = self.path[1:].upper() + "s"
            method_name = 'do_' + self.command.upper()
        else:
            list_name = self.path[1:second_slash].upper() + "s"
            verb_name = '_' + self.path[(second_slash + 1):].lower()
            method_name = 'do_' + self.command.upper() + verb_name 
        return list_name, method_name

    def __write(self, key: SEL):
        try:
            while True:
                message = key.data.outgoing_messages.get_nowait()
                key.fileobj.sendall(message)
        except queue.Empty:
            key.data.callback = self.__read
            self.sel.modify(key.fileobj, selectors.EVENT_READ, key.data)
        except OSError as ose:
            self.log_error(ose)
            key.data.close_connection = True
        finally:
            if key.data.close_connection:
                self.log_message(f'Closed the connection.')
                self.__shutdown_connection(key)

    def __shutdown_connection(self, key: SEL):
        logging.info(f'{key.data.addr[0]} - - Closing connection.')
        self.sel.unregister(key.fileobj)
        key.fileobj.shutdown(socket.SHUT_RDWR)
        key.fileobj.close()

def main():
    broker = Broker()
    broker.listen()

if __name__ == "__main__":
    main()
