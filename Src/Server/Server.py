import atexit
import logging
import asyncio
import http.client
import queue
import os
import Routes
from typing import List, Dict
from logging.handlers import TimedRotatingFileHandler
from http import HTTPStatus
from copy import copy
from socket import *
from time import time
from selectors import *
from ipaddress import IPv4Address, ip_network
from Wrap_HTTPRequestHandler import Wrap_HTTPRequestHandler
from types import SimpleNamespace
from io import BytesIO
from Device import Device
from CANNodes import CANNodes
from SensorNodes import SensorNodes

"""TODO Notes:
    - When recving or sending timeout should be calculated dynamically.
        - From:
          https://www.geeksforgeeks.org/algorithm-for-dynamic-time-out-timer-calculation/
            - Use Karn's Modification with Jacob's Algorithm to dynamically
              calculate timeout and when to retransmit.
"""

# COPIED FROM: https://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output?page=1&tab=votes#tab-top
class ColoredConsoleHandler(logging.StreamHandler):
    def emit(self, record):
        # Need to make a actual copy of the record
        # to prevent altering the message for other loggers
        myrecord = copy(record)
        levelno = myrecord.levelno
        if(levelno >= 50):  # CRITICAL / FATAL
            color = '\x1b[31m'  # red
        elif(levelno >= 40):  # ERROR
            color = '\x1b[31m'  # red
        elif(levelno >= 30):  # WARNING
            color = '\x1b[33m'  # yellow
        elif(levelno >= 20):  # INFO
            color = '\x1b[32m'  # green
        elif(levelno >= 10):  # DEBUG
            color = '\x1b[35m'  # pink
        else:  # NOTSET and anything else
            color = '\x1b[0m'  # normal
        myrecord.levelname = color + str(myrecord.levelname) + '\x1b[0m'  # normal
        logging.StreamHandler.emit(self, myrecord)
# ------------------------------------------------------------

class Broker(Wrap_HTTPRequestHandler):

    def __init__(self) -> None:
        self.client_address = None
        self.keepalive_interval = 300
        self.protocol_version = "HTTP/1.1"
        atexit.register(self.__exit)
        self.__setup_logging()
        self.log_message("Broker Initializing.")
        self.sel = DefaultSelector()
        self.multicast_ips: List[Dict] = self.__init_multicast_ips()
        self.blacklist_ips: List[IPv4Address] = []
        self.SSSFs = CANNodes(self.sel, self.multicast_ips)
        self.CONTROLLERs = SensorNodes(self.sel, self.multicast_ips)
        self.__setup()

    def __findpath(self, log_name: str) -> str:
        base_dir = os.path.abspath(os.getcwd())
        for root, dirs, files in os.walk(base_dir):
            for name in dirs:
                if name == "Logs":
                    log_path = os.path.join(root, name)
                    return os.path.join(log_path, log_name)
        log_path = os.path.join(base_dir, "Logs")
        return os.path.join(log_path, log_name)

    def __setup_logging(self) -> None:
        filename = self.__findpath("broker_log")
        logging.basicConfig(
            format='%(asctime)-15s %(module)-10.10s %(levelname)s %(message)s',
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

    def __init_multicast_ips(self) -> List[Dict]:
        ips = []
        for ip in ip_network('239.255.0.0/16'):
            ips.append({
                "ip": ip,
                "available": True,
                "sockets": []
            })
        return ips

    def __setup(self):
        self.lsock = socket(AF_INET, SOCK_STREAM)
        self.lsock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.lsock.setblocking(False)
        data = SimpleNamespace(callback=self.__accept)
        self.sel.register(self.lsock, EVENT_READ, data=data)

    def listen(self) -> None:
        device_address = gethostbyname_ex(gethostname())[2]
        self.lsock.bind(('', 80))
        self.lsock.listen()
        self.log_message(
            f'Listening on these interfaces: {device_address}:80'
            )
        asyncio.run(self.__listening_loop())

    async def __listening_loop(self) -> None:
        while True:
            try:
                events = self.sel.select(timeout=1)
            except TimeoutError:
                continue
            except KeyboardInterrupt:
                return
            else:
                cors = [self.__events(key, mask) for key, mask in events]
                await asyncio.gather(*cors)
                self.__prune_connections()

    async def __events(self, key: SelectorKey, mask):
        if mask == EVENT_READ and key.data.callback != self.__accept:
            if not key.data.rate_limit(self.log_error):
                await asyncio.sleep(0.2)
                self.__call_callback(key)
        else:
            self.__call_callback(key)

    def __call_callback(self, key: SelectorKey):
        if hasattr(key.data, "addr"):
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
            data = Device(self.__read, self.__write, addr)
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
            self.key = key
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
                self.__shutdown_connection(key)

    def __handle_response(self, key: SelectorKey):
        key.data.response = http.client.HTTPResponse(key.fileobj)
        try:
            key.data.response.begin()
            key.data.expecting_response = False
        except (
            http.client.HTTPException,
            http.client.BadStatusLine,
            OSError
            ) as ose:
            self.log_error(f'{ose}')
            key.data.close_connection = True
            self.__shutdown_connection(key)

    def do_GET(self):
        self.__method_proxy()

    def do_HEAD(self):
        self.__method_proxy()

    def do_POST(self):
        self.__method_proxy()

    def do_PUT(self):
        self.__method_proxy()

    def do_DELETE(self):
        self.__method_proxy()

    def do_OPTIONS(self):
        self.__method_proxy()

    def do_CONNECT(self):
        self.__method_proxy()

    def do_TRACE(self):
        self.__method_proxy()

    def __parse_path(self) -> str:
        second_slash = self.path.find('/', 1)
        if second_slash == -1:
            list_name = self.path[1:].upper() + "s"
        else:
            list_name = self.path[1:second_slash].upper() + "s"
        return list_name

    def __method_proxy(self):
        try:
            device_list = getattr(self, self.__parse_path())
            func = Routes.routes[self.path.upper() + self.command.upper()]
            response = func(device_list, self.key, self.rfile, self.wfile)
            if response == HTTPStatus.FORBIDDEN:
                self.blacklist_ips.append(self.key.addr[0])
                self.key.data.close_connection = True
            self.send_response(response)
        except (KeyError, AttributeError) as ae:
            logging.warning(ae)
            self.log_error(
                "Requested a URI+Command combination "
                "that was not found."
                )
            self.send_error(HTTPStatus.NOT_FOUND)

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
            if key.data.close_connection: self.__shutdown_connection(key)

    def __shutdown_connection(self, key: SelectorKey) -> None:
        logging.info(f'{key.data.addr[0]} - Closing connection.')
        try:
            valid_type = hasattr(key.data, "type") and key.data.type != "unknown"
            in_use = hasattr(key.data, "in_use") and key.data.in_use
            if valid_type and in_use:
                del_method = "/" + key.data.type.upper() + "/REGISTERDELETE"
                del_method = Routes.routes[del_method]
                with BytesIO() as self.wfile, BytesIO() as self.rfile:
                    del_method(
                        getattr(self, key.data.type + "s"), key,
                        self.wfile, self.rfile
                        )
        except (KeyError, AttributeError) as ae:
            logging.error(ae)
        self.sel.unregister(key.fileobj)
        key.fileobj.shutdown(SHUT_RDWR)
        key.fileobj.close()

    def __exit(self) -> None:
        self.sel.close()

def main():
    broker = Broker()
    broker.listen()

if __name__ == "__main__":
    main()
