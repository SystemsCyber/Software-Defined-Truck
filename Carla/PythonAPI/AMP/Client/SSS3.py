import socket
import struct
import sys
import time
import os
import selectors
from typing import Union, Tuple, List, Dict, Optional
from frame import Frame
from types import SimpleNamespace
import logging
from logging.handlers import TimedRotatingFileHandler
from HelperMethods import ColoredConsoleHandler
from BrokerHandle import BrokerHandle
import shutil
from ipaddress import IPv4Address
# import multiprocessing as mp
import threading

# Type Aliases
SOCK_T = socket.socket
SEL = selectors.SelectorKey
if sys.version_info >= (3, 9):
    SOCK_DICT = dict[str, SOCK_T]
    MCAST_SOCKS = tuple[str, SOCK_DICT]
    ADDR_T = tuple[str, int]
    ADDR_LIST = list[ADDR_T]
    RETURN_ADDR_LIST = list[Union[ADDR_T, None]]
else:
    SOCK_DICT = Dict[str, SOCK_T]
    MCAST_SOCKS = Tuple[str, SOCK_DICT]
    ADDR_T = Tuple[str, int]
    ADDR_LIST = List[ADDR_T]
    RETURN_ADDR_T = List[Union[ADDR_T, None]]

class tcolors:
    bold = '\u001b[1m'
    black = '\u001b[30m'
    red = '\u001b[31m'
    green  = '\u001b[32m'
    yellow = '\u001b[33m'
    blue = '\u001b[34m'
    magenta = '\u001b[35m'
    cyan = '\u001b[36m'
    white = '\u001b[37m'
    reset = '\u001b[0m'

class SSS3:
    """SSS3 communication utility in conjunction with the CARLA simulator"""

    def __init__(self, _server_address = socket.gethostname()) -> None:
        self.__setup_logging()
        self.frame = Frame()
        self.dropped_messages = 0
        self.timeouts = 0
        self.seq_miss_match = 0
        self.sel = selectors.DefaultSelector()
        # self.broker = BrokerHandle(self.sel, _server_address)
        self.broker = BrokerHandle(self.sel, "192.168.1.58")
        self.can = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.carla = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.l_thread = threading.Thread(target=self.__listen, args=(0,))
        self.l_thread.setDaemon(True)
        self.selector_lock = threading.Lock()
        self.listen = True

    def __listen(self, _timeout=None, waiting_msg = None) -> None:
        if waiting_msg:
            self.__typewritter(waiting_msg, tcolors.cyan)
        while self.listen:
            try:
                with self.selector_lock:
                    connection_events = self.sel.select(timeout=_timeout)
                    for key, mask in connection_events:
                        callback = key.data.callback
                        callback(key)  
            except TimeoutError:
                continue
            except KeyboardInterrupt:
                return

    def __setup_logging(self) -> None:
        logging.basicConfig(
            format='%(asctime)s - %(filename)s - %(levelname)s - %(message)s',
            level=logging.DEBUG,
            handlers=[
                TimedRotatingFileHandler(
                    filename="sss3_log",
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

    def setup(self):
        if self.broker.connect():
            if self.broker.register():
                self.__select_devices(self.broker.get_devices())
            else:
                logging.error("Request to register with server failed.")
        else:
            logging.error("Could not connect to the server.")

    def __select_devices(self, devices: list):
        if len(devices) > 0:
            self.__print_devices(devices)
            self.__typewritter("Enter the numbers corresponding to the ECUs you would like to use (comma separated): ", tcolors.magenta, end=None)
            input_list = input('').split(',')
            requested_devices = [int(i.strip()) for i in input_list]
            self.__request_devices(requested_devices, devices)
            data = SimpleNamespace(
                callback = self.__receive_SSE,
                outgoing_message = None
                )
            self.sel.modify(self.broker.ctrl.sock, selectors.EVENT_READ, data)
            self.start(self.broker.mcast_IP, self.broker.can_port, self.broker.carla_port)
        else:
            self.__greeting_bar()
            self.__typewritter("Unfortunately, there are no available ECUs right now. Please check back later.", tcolors.red)

    def __print_devices(self, devices: list) -> None:
        self.__greeting_bar()
        self.__typewritter("Available ECUs: ", tcolors.magenta)
        for device in devices:
            print(f'{device["ID"]}):')
            for ecu in device["ECUs"]:
                print(f'\tType: {ecu["type"]} | Year: {ecu["year"]} | ', end="")
                print(f'Make: {ecu["make"]} | Model: {ecu["model"]}', end="\n\n")

    def __request_devices(self, requestedECUs: list, devices: list):
        if self.broker.request_devices(requestedECUs, devices):
            self.__typewritter("Requested devices were successfully allocated.", tcolors.yellow)
        else:
            self.__typewritter("One or more of the requested devices are no longer available. Please select new device(s).", tcolors.red)
            self.__select_devices(self.broker.get_devices())

    def __typewritter(self, sentence, color=None, end='\n'):
        print(color, end='')
        for char in sentence:
            print(char, sep='', end='', flush=True)
            time.sleep(0.01)
        print(tcolors.reset, end=end)

    def __greeting_bar(self):
        # os.system('cls' if os.name == 'nt' else 'clear')
        term_size = shutil.get_terminal_size()
        greeting_message = "* ECU Selection Menu *"
        print(f'{tcolors.green}{greeting_message:*^{term_size[0]-5}}{tcolors.reset}')

    def __receive_SSE(self, key: selectors.SelectorKey):
        try:
            self.broker.receive_SSE(key)
        except SyntaxError as se:
            logging.error(se)
        else:
            if self.broker.command.lower() == "post":
                self.start(self.broker.mcast_IP, self.broker.can_port, self.broker.carla_port)
            elif self.broker.command.lower() == "delete":
                self.stop()

    def start(self, mcast_IP: IPv4Address, can_port: int, carla_port: int):
        self.__typewritter("Received session setup information from the server.", tcolors.magenta)
        self.__typewritter("Starting the session!", tcolors.yellow)
        self.__set_mcast_options(self.can, mcast_IP, can_port)
        can_data = SimpleNamespace(callback = self.__receive)
        self.sel.register(self.can, selectors.EVENT_READ, can_data)
        self.__set_mcast_options(self.carla, mcast_IP, carla_port)
        carla_data = SimpleNamespace(
            callback = self.__send,
            outgoing_message = None
            )
        self._key = self.sel.register(self.carla, selectors.EVENT_READ, carla_data)
        if self.l_thread.is_alive():
            self.listen = False
            self.l_thread.join(1)
            self.listen = True
            self.l_thread.start()
        else:
            self.listen = True
            self.l_thread.start()
            try:
                time.sleep(1000)
            except KeyboardInterrupt:
                pass
                
    def __set_mcast_options(self, sock: socket.socket, mcast_IP: IPv4Address, port: int) -> None:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
        sock.bind(('', port))
        group = socket.inet_aton(str(mcast_IP))
        mreq = struct.pack("4sl", group, socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP,
                        socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(0.4)

    def stop(self):
        self.__typewritter("Stopping session.", tcolors.red)
        self.listen = False
        self.broker.send_delete("/session")
        self.broker.send_delete("/client/register", True)
        logging.debug("Unregistering can socket.")
        self.sel.unregister(self.can)
        logging.debug("Shutting down the can socket.")
        self.can.shutdown(socket.SHUT_RDWR)
        logging.debug("Closing the can socket.")
        self.can.close()
        logging.debug("Unregistering carla socket.")
        self.sel.unregister(self.carla)
        logging.debug("Shutting down the carla socket.")
        self.carla.shutdown(socket.SHUT_RDWR)
        logging.debug("Closing the carla socket.")
        self.carla.close()

    def send_control_frame(self, control):
        with self.selector_lock:
            self.frame.frame_num += 1
            message = self.frame.pack(control)
            self._key.data.outgoing_message = message
            self.sel.modify(self._key.fileobj, selectors.EVENT_WRITE, self._key.data)

    def __send(self, key: selectors.SelectorKey) -> None:
        try:
            message = key.data.outgoing_message
            key.fileobj.sendto(message, (self.mcast_ip, self.carla_port))
            self.sel.modify(key.fileobj, selectors.EVENT_READ, key.data)
        except InterruptedError:
            logging.error("Message was interrupted while sending.")
        except BlockingIOError:
            logging.error("Socket is currently blocked and cannot send messages.")

    def __receive(self, key: selectors.SelectorKey) -> None:
        try:
            data = key.fileobj.recv(20)
            if len(data) == 20:  # 20 is size of carla struct in bytes
                ecm_data = struct.unpack("Ifff???B", data)
                print(self.frame.print_frame(self.frame.unpack(ecm_data)))
                # if not self.frame(ecm_data, control, verbose):
                #     self.__frame_miss_match(ecm_data, verbose)
        except socket.timeout:
            key.fileobj.settimeout(0.04)
            self.dropped_messages += 1
            self.timeouts += 1
            logging.warning(f'Socket Timeout. Total: {self.timeouts}')

    # def __frame_miss_match(self, ecm_data, verbose=False) -> None:
    #     self.dropped_messages += 1
    #     self.seq_miss_match += 1
    #     self.can.settimeout(0.01)
    #     for i in range(self.frame.last_frame - ecm_data[0]):
    #         self.can.recv(20)
    #         self.dropped_messages += 1
    #         self.seq_miss_match += 1
    #     self.can.settimeout(0.04)
    #     if verbose:
    #         print(ecm_data[0])
    #         print(self.frame.last_frame)
    #         print(
    #             f'Sequence number miss match. Total: {self.seq_miss_match}')


if __name__ == '__main__':
    sss3object = SSS3()
    sss3object.setup()
