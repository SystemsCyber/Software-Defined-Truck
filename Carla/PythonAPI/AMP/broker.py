from http import HTTPStatus
import queue
import socket
import os
import time
import sys
import selectors
import ipaddress
from http.server import BaseHTTPRequestHandler
from types import SimpleNamespace
from typing import Tuple, Dict, Union, List, Optional
from types import SimpleNamespace
from io import BytesIO
from SSS3Handle import SSS3Handle
from ClientHandle import ClientHandle
from Device import Device
import logging
from logging.handlers import TimedRotatingFileHandler
from HelperMethods import ColoredConsoleHandler

"""TODO Notes:
    - We need to set the keep alive function on the teensy.
    - We need to close connections if they don't register their device within a
      few seconds after connecting.
    - We don't need to scan the multicast address range because we can bind to a
      specific interface via socket options.
    - Use the built in socket keep alive options to send "heartbeats" to the
      devices. Refer to this for more information:
      https://stackoverflow.com/questions/12248132/how-to-change-tcp-keepalive-timer-using-python-script
      and https://docs.microsoft.com/en-us/windows/win32/winsock/so-keepalive
      
    - Send error when protocol/method not supported. Use
      HTTPStatus.NOT_IMPLEMENTED.
    - Add error checking for IndexError when using Regex
    - When recving or sending timeout should be calculated dynamically.
        - From:
          https://www.geeksforgeeks.org/algorithm-for-dynamic-time-out-timer-calculation/
            - Use Karn's Modification with Jacob's Algorithm to dynamically
              calculate timeout and when to retransmit.
        - Sockets don't expose ack so we can either make sure that we respond to messages so that both sides can calculate RTT or we can send pings. Unfortunately the 
        - | ==================== Ignore ================== |
        - Sockets don't expose ack so instead of sending multiple messages we
          can get this information by pinging the device.
        - Be careful:
            - Don't use os.system. Use the safer alternative -> subprocess
            - Use subprocess.popen as it spawns another process to do this
              operation so that it doesn't slow down the main thread.
            - If you use subprocess to run the ping command make sure to set the
              shell argument to false.
            - Don't use the pure python ping library because root is required on
              linux to create ICMP sockets.
            - No matter the method of doing this make sure that
            - Example:
                import os
                import subprocess
                
                number_of_messages = "-n" if os.name == 'nt' else "-c"
                host = "www.google.com"

                ping = subprocess.Popen(
                    ["ping", number_of_messages, "4", host],
                    stdout = subprocess.PIPE,
                    stderr = subprocess.PIPE
                )

                out, error = ping.communicate()
                print out
        - | ============================================= |
    - When sending make sure to use send all and possibly flush as well.
    - Send any errors that are raised via parsing, sending, or receiving.
    - Use a token bucket algorithm to rate limit clients and devices.
    - From:
        https://stackoverflow.com/questions/667508/whats-a-good-rate-limiting-algorithm
        rate = 5.0; // unit: messages
        per  = 8.0; // unit: seconds
        allowance = rate; // unit: messages
        last_check = now(); // floating-point, e.g. usec accuracy. Unit: seconds

        when (message_received):
        current = now();
        time_passed = current - last_check;
        last_check = current;
        allowance += time_passed * (rate / per);
        if (allowance > rate):
            allowance = rate; // throttle
        if (allowance < 1.0):
            discard_message();
        else:
            forward_message();
            allowance -= 1.0;
    - 
"""

# Type Aliases
SOCKTYPE = socket.socket
if sys.version_info >= (3, 9):
    MCAST_IP_ENTRY = (str, None | SOCKTYPE)
    MCAST_IPS = list[MCAST_IP_ENTRY]
    SSS3_ENTRY = selectors.SelectorKey
    SSS3S = list[SSS3_ENTRY]
    CARLA_CLIENT = selectors.SelectorKey
    CARLA_CLIENTS = list[CARLA_CLIENT]
    SAFE_LIST = MCAST_IPS | SSS3S | CARLA_CLIENTS
    SAFE_ENTRY = MCAST_IP_ENTRY | SSS3_ENTRY | CARLA_CLIENT
    SOCK_DICT = dict[str, SOCKTYPE]
    SAFE_INDEX = (int, int | str | None)
    CONN_HANDLE = (SOCKTYPE, (str, int))
else:
    MCAST_IP_ENTRY = Tuple[str, Union[None, SOCKTYPE]]
    MCAST_IPS = List[MCAST_IP_ENTRY]
    SSS3_ENTRY = selectors.SelectorKey
    SSS3S = List[SSS3_ENTRY]
    CARLA_CLIENT = selectors.SelectorKey
    CARLA_CLIENTS = List[CARLA_CLIENT]
    SAFE_LIST = Union[MCAST_IPS, SSS3S, CARLA_CLIENTS]
    SAFE_ENTRY = Union[MCAST_IP_ENTRY, SSS3_ENTRY, CARLA_CLIENT]
    SOCK_DICT = Dict[str, SOCKTYPE]
    SAFE_INDEX = Tuple[int, Union[int, str, None]]
    CONN_HANDLE = Tuple[SOCKTYPE, Tuple[str, int]]


class Broker(BaseHTTPRequestHandler):

    # ==================== Initialization ====================

    def __init__(self, _host_port=41660, _carla_port=41664, _can_port=41665) -> None:
        self.__setup_logging()
        self.host_port = _host_port
        self.carla_port = _carla_port
        self.can_port = _can_port
        self.__log_init()
        self.sel = selectors.DefaultSelector()
        self.multicast_IPs = self.__init_multicast_ip_list()
        self.blacklist_ips = []
        self.SSS3s = SSS3Handle(self.sel, self.blacklist_ips)
        self.CLIENTs = ClientHandle(self.sel, self.blacklist_ips)

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

    def __init_multicast_ip_list(self):
        multicast_ips = []
        for ip in ipaddress.ip_network('239.255.0.0/16'):
            multicast_ips.append({
                "ip": ip,
                "available": False,
                "sockets": []
            })
        return multicast_ips

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

    def __log_init(self) -> None:
        msg = f"Broker initializing with these settings:\n"
        msg += f"\tHost Address: {socket.gethostname()}\n"
        msg += f"\tHost Port: {self.host_port}\n"
        msg += f"\tCarla Port: {self.carla_port}\n"
        msg += f"\tCAN Port: {self.can_port}\n"
        self.log_message(msg)

    # ==================== Main Server Functions ====================

    def listen(self):
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lsock.bind((socket.gethostname(), self.host_port))
        lsock.listen()
        lsock.setblocking(False)
        data = SimpleNamespace(callback=self.__accept)
        self.sel.register(lsock, selectors.EVENT_READ, data=data)
        print(f'Listening on: {socket.gethostname()}:{self.host_port}')
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
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
        else:
            self.__set_keepalive(conn, 300000, 300000)
            print(f'New connection from: {addr[0]}:{str(addr[1])}')
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
                pass

    def __rate_limit(self, key: selectors.SelectorKey) -> bool:
        now = time.time()
        key.data.allowance += (now - key.data.last_check) * key.data.rate
        key.data.last_check = now
        if (key.data.allowance > key.data.rate):
            key.data.allowance = key.data.rate
        if (key.data.allowance < 1.0):
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
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            method_handle = getattr(device_list, method_name)
            self.send_response(method_handle(self._key, self.rfile))
        except AttributeError:
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
            key.data.close_connection = True
        except BlockingIOError:
            pass
        finally:
            if key.data.close_connection:
                self.__shutdown_connection(key)

    def __shutdown_connection(self, key: selectors.SelectorKey):
        # Stop monitoring the socket
        self.sel.unregister(key.fileobj)
        # Close the socket
        key.fileobj.shutdown(socket.SHUT_RDWR)
        key.fileobj.close()

def main():
    broker = Broker()
    broker.listen()


if __name__ == "__main__":
    main()
