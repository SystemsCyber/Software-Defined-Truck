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
from HelperMethods import ColoredConsoleHandler

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

class Broker(BaseHTTPRequestHandler):

    # ==================== Initialization ====================

    def __init__(self) -> None:
        self.__setup_logging()
        self.log_sys_message("Broker Initializing.")
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
        self.SSS3s = SSS3Handle(self.sel, self.blacklist_ips)
        self.CLIENTs = ClientHandle(self.sel, self.blacklist_ips, self.multicast_IPs)

    def __setup_logging(self):
        logging.basicConfig(
            format='%(asctime)s - %(filename)s - %(levelname)s - %(message)s',
            level=logging.DEBUG,
            handlers=[
                TimedRotatingFileHandler(
                    filename="broker_log.log",
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

    def log_sys_error(self, format, *args):
        logging.error("%s - - %s\n" % ("SERVER", format%args))

    def log_sys_message(self, format, *args):
        logging.info("%s - - %s\n" % ("SERVER", format%args))

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
        self.send_header("content-length", str(len(message_body)))
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
        lsock.bind((socket.gethostname(), 80))
        lsock.listen()
        lsock.setblocking(False)
        data = SimpleNamespace(callback=self.__accept)
        self.sel.register(lsock, selectors.EVENT_READ, data=data)
        self.log_sys_message(f'Listening on: {socket.gethostname()}:80')
        self.__wait_for_connection()

    def __wait_for_connection(self) -> None:
        while True:
            try:
                connection_events = self.sel.select(timeout=1)
                for key, mask in connection_events:
                    self._key = key
                    callback = key.data.callback
                    callback(key)
                self.__drop_loose_connections()
            except TimeoutError:
                continue
            except KeyboardInterrupt:
                return

    def __drop_loose_connections(self) -> None:
        """Loose connections are accepted connections from devices that don't
        register within 5 seconds of connecting."""
        sel_map = self.sel.get_map()
        try:
            for fd in sel_map:
                key = sel_map[fd]
                not_accepted = hasattr(key.data, "accept_by") and (
                    key.data.MAC == "unknown")
                if not_accepted and (key.data.accept_by < time.time()):
                    msg = f'{key.data.addr[0]} has not registered within 5 '
                    msg += f'seconds of first connecting. Closing connection.'
                    self.log_sys_message(msg)
                    self.__shutdown_connection(key)
        except RuntimeError:
            return

    def __accept(self, key: selectors.SelectorKey) -> None:
        """Takes a new connection from the listening socket and assigns it its
        own socket. Then registers it with the selectors using the READ mask.
        """
        conn, addr = key.fileobj.accept()
        conn.setblocking(False)
        if addr[0] in self.blacklist_ips:
            self.log_sys_error(f'Blacklisted IP address: {addr[0]} tried to connect.')
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
        else:
            self.log_sys_message(f'New connection from: {addr[0]}:{str(addr[1])}')
            self.__set_keepalive(conn, 300000, 300000)
            data = Device(self.__read, addr)
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

    def __read(self, key: selectors.SelectorKey):
        if not self.__rate_limit(key):
            try:
                self._key = key
                self.client_address = self._key.data.addr
                self.__handle_request(self._key.fileobj.recv(4096))
                self.sel.modify(self._key.fileobj,
                                selectors.EVENT_WRITE, self._key.data)
            except BlockingIOError:
                self.log_error("A blocking error occured in __read, when it shouldn't have.")
            except ConnectionResetError as cre:
                key.data.close_connection = True
                self.log_error(f'{cre}')

    def __rate_limit(self, key: selectors.SelectorKey) -> bool:
        # Token Bucket algorithm
        now = time.time()
        key.data.allowance += (now - key.data.last_check) * key.data.rate
        key.data.last_check = now
        if (key.data.allowance > key.data.rate):
            key.data.allowance = key.data.rate
        if (key.data.allowance < 1.0):
            self.log_sys_error(f'Rate limiting {key.data.addr[0]}')
            return True
        else:
            key.data.allowance -= 1.0
            return False

    def __handle_request(self, message: bytes) -> None:
        with BytesIO() as self.wfile, BytesIO(message) as self.rfile:
            self.handle_one_request()
            self.end_headers()
            self.wfile.seek(0)
            self._key.data.outgoing_messages.put(self.wfile.read())
            self._key.data.callback = self.__write
            self._key.data.close_connection = self.close_connection

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
        except AttributeError:
            self.log_error("Requested a non-existent device type.")
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            method_handle = getattr(device_list, method_name)
            self.send_response(method_handle(self._key, self.rfile, self.wfile))
            if not self.close_connection:
                self.send_header("connection", "keep-alive")
        except AttributeError:
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

    def __write(self, key: selectors.SelectorKey):
        try:
            while True:
                message = key.data.outgoing_messages.get_nowait()
                key.fileobj.sendall(message)
        except queue.Empty:
            key.data.callback = self.__read
            self.sel.modify(key.fileobj, selectors.EVENT_READ, key.data)
        except InterruptedError:
            msg = f'{key.data.addr[0]} - - Interrupted while sending message. '
            msg += f'This is an unrecoverable error. Closing connection.'
            logging.error(msg)
            key.data.close_connection = True
        except BlockingIOError:
            msg = f'{key.data.addr[0]} - - A blocking error occured in '
            msg += f'__write, when it shouldnt have.'
            logging.error(msg)
        finally:
            if key.data.close_connection:
                logging.info(f'{key.data.addr[0]} - - Closed the connection.')
                self.__shutdown_connection(key)

    def __shutdown_connection(self, key: selectors.SelectorKey):
        logging.info(f'{key.data.addr[0]} - - Closing connection.')
        self.sel.unregister(key.fileobj)
        key.fileobj.shutdown(socket.SHUT_RDWR)
        key.fileobj.close()

def main():
    broker = Broker()
    broker.listen()


if __name__ == "__main__":
    main()
