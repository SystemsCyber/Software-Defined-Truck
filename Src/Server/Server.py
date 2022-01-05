from http import HTTPStatus
from argparse import ArgumentParser
import queue
from socket import *
from time import time, sleep
from selectors import *
from ipaddress import ip_network
from http.server import BaseHTTPRequestHandler
from types import SimpleNamespace
from io import BytesIO
from Node import Node
from CANNodes import CANNodes
from SensorNodes import SensorNodes
import logging
from logging.handlers import TimedRotatingFileHandler
from HelperMethods import ColoredConsoleHandler, LogFolder
import http.client

"""TODO Notes:
    - When recving or sending timeout should be calculated dynamically.
        - From:
          https://www.geeksforgeeks.org/algorithm-for-dynamic-time-out-timer-calculation/
            - Use Karn's Modification with Jacob's Algorithm to dynamically
              calculate timeout and when to retransmit.
"""

class Broker(BaseHTTPRequestHandler):

    # ==================== Initialization ====================

    def __init__(self, _keepalive_interval = 300, _localhost = False) -> None:
        self.client_address = None
        self.keepalive_interval = _keepalive_interval
        self.localhost = _localhost
        self.__setup_logging()
        self.log_message("Broker Initializing.")
        self.protocol_version = "HTTP/1.1"
        self.sel = DefaultSelector()
        self.multicast_IPs = []
        for ip in ip_network('239.255.0.0/16'):
            self.multicast_IPs.append({
                "ip": ip,
                "available": True,
                "sockets": []
            })
        self.blacklist_ips = []
        self.SSS3s = CANNodes(self.sel, self.multicast_IPs)
        self.CLIENTs = SensorNodes(self.sel, self.multicast_IPs)

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
        if self.client_address:
            address_string = self.client_address[0]
        logging.error("%s - - %s\n" %
                         (address_string, format%args))

    def log_message(self, format, *args):
        address_string = "SERVER"
        if self.client_address:
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
        lsock = socket(AF_INET, SOCK_STREAM)
        lsock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        device_address = gethostbyname_ex(gethostname())[2][1]
        lsock.bind((device_address, 80))
        # lsock.bind(("127.0.0.1", 80))
        lsock.listen()
        lsock.setblocking(False)
        data = SimpleNamespace(callback=self.__accept)
        self.sel.register(lsock, EVENT_READ, data=data)
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

    def __handle_mask_events(self, key: SelectorKey, mask):
        if mask == EVENT_READ:
            if key.data.callback == self.__accept:
                callback = key.data.callback
                callback(key)
            elif not key.data.rate_limit(self.log_error):
                sleep(0.001)  # Small hack to let the rest of the message
                                    # make it in to the socket before reading it.
                self.__call_callback(key)
        else:
            self.__call_callback(key)

    def __call_callback(self, key: SelectorKey):
        self.client_address = key.data.addr
        callback = key.data.callback
        callback(key)
        self.client_address = None

    def __prune_connections(self) -> None:
        """Loose connections are accepted connections from devices that don't
        register within 30 seconds of connecting."""
        current_time = time()
        sel_map = self.sel.get_map()
        for fd in sel_map:
            key = sel_map[fd]
            not_lsock = hasattr(key.data, "MAC")
            if not_lsock and key.data.is_loose(current_time, self.log_error):
                key.data.close_connection = True
                self.sel.modify(key.fileobj, EVENT_WRITE, key.data)

    def __accept(self, key: SelectorKey) -> None:
        """Takes a new connection from the listening socket and assigns it its
        own socket. Then registers it with the selectors using the READ mask.
        """
        conn, addr = key.fileobj.accept()
        conn.setblocking(False)
        if addr[0] in self.blacklist_ips:
            self.log_error(f'Blacklisted IP address: {addr[0]} tried to connect.')
            conn.shutdown(SHUT_RDWR)
            conn.close()
        else:
            self.log_message(f'New connection from: {addr[0]}:{str(addr[1])}')
            self.__set_keepalive(conn)
            data = Node(self.__read, self.__write, addr)
            self.sel.register(conn, EVENT_READ, data=data)

    def __set_keepalive(self, conn: SocketType) -> None:
            conn.setsockopt(SOL_SOCKET, SO_KEEPALIVE, 1)
            conn.setsockopt(IPPROTO_TCP, TCP_KEEPIDLE, self.keepalive_interval)
            conn.setsockopt(IPPROTO_TCP, TCP_KEEPINTVL, self.keepalive_interval)
            conn.setsockopt(IPPROTO_TCP, TCP_KEEPCNT, 3)

    def __read(self, key: SelectorKey):
        if key.data.expecting_response:
            self.__handle_response(key)
        else:
            try:
                message = key.fileobj.recv(4096)
            except OSError as ose:
                self.log_error(f'{ose}')
                key.data.close_connection = True
                self.__shutdown_connection(key)
            else:
                self.__handle_request(key, message)
    
    def __handle_request(self, key: SelectorKey, message: bytes) -> None:
        with BytesIO() as self.wfile, BytesIO(message) as self.rfile:
            self._key = key
            self.handle_one_request()
            self.end_headers()
            self.wfile.seek(0)
            outgoing = self.wfile.read()
            if len(outgoing) > 0:
                key.data.outgoing_messages.put(outgoing)
                key.data.callback = self.__write
                key.data.close_connection = self.close_connection
                self.sel.modify(key.fileobj, EVENT_WRITE, key.data)
            else:
                logging.info(f'{key.data.addr[0]} - - Closed the connection.')
                self.__shutdown_connection(key)

    def __handle_response(self, key: SelectorKey):
        key.data.response = http.client.HTTPResponse(key.fileobj)
        try:
            key.data.response.begin()
            key.data.expecting_response = False
        except http.client.HTTPException as he:
            self.log_error(f'{he}')
            key.data.close_connection = True
            self.__shutdown_connection(key)
        except OSError as ose:
                self.log_error(f'{ose}')
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
            logging.debug(f'{ae}')
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
            logging.debug(f'{ae}')
            print(self.path)
            print(self.command)
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

    def __write(self, key: SelectorKey):
        try:
            while True:
                message = key.data.outgoing_messages.get_nowait()
                key.fileobj.sendall(message)
        except queue.Empty:
            key.data.callback = self.__read
            self.sel.modify(key.fileobj, EVENT_READ, key.data)
        except OSError as ose:
            self.log_error(f'{ose}')
            key.data.close_connection = True
        finally:
            if key.data.close_connection:
                self.log_message(f'Closed the connection.')
                self.__shutdown_connection(key)

    def __shutdown_connection(self, key: SelectorKey):
        logging.info(f'{key.data.addr[0]} - - Closing connection.')
        try:
            if getattr(key.data, "type"):
                list_name = getattr(self, key.data.type + "s")
                del_method = getattr(list_name, "do_DELETE_register")
                del_method(key)
        except AttributeError as ae:
            logging.error(ae)
        self.sel.unregister(key.fileobj)
        key.fileobj.shutdown(SHUT_RDWR)
        key.fileobj.close()

def main():
    argparser = ArgumentParser(
        description="DARPA AMP CARLA Broker"
        )
    argparser.add_argument(
        '-k', '--keep_alive_interval',
        default=300,
        type=int,
        help='Keep alive probe interval for sockets.'
        )
    argparser.add_argument(
        '-l', '--localhost',
        action='store_true',
        default=False,
        help='Use localhost interface for listening socket.'
    )
    args = argparser.parse_args()
    broker = Broker(args.keep_alive_interval, args.localhost)
    broker.listen()

if __name__ == "__main__":
    main()
