import socket
import struct
import sys
import time
import subprocess
import os
import re
import selectors
from typing import Union, Tuple, List, Dict, Optional
from frame import Frame
from types import SimpleNamespace
import logging
from logging.handlers import TimedRotatingFileHandler
from HelperMethods import ColoredConsoleHandler
from BrokerHandle import BrokerHandle
import shutil

# Type Aliases
SOCK_T = socket.socket
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
        self.carla_port = 0
        self.can_port = 0
        self.frame = Frame()
        self.dropped_messages = 0
        self.timeouts = 0
        self.seq_miss_match = 0
        self.sel = selectors.DefaultSelector()
        self.broker = BrokerHandle(self.sel, _server_address)

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
            self.__request_devices([int(i.strip()) for i in input_list])
            data = SimpleNamespace(callback = self.__parse_session_message)
            self.sel.modify(self.broker.ctrl.sock, selectors.EVENT_READ, data)
            self.__listen(5, "Waiting for setup message from server...")
        else:
            self.__greeting_bar()
            self.__typewritter("Unfortunately, there are no available ECUs right now. Please check back later.", tcolors.red)

    def __print_devices(self, devices: list) -> None:
        self.__greeting_bar()
        self.__typewritter("Available ECUs: ", tcolors.magenta)
        for i in range(len(devices)):
            print(f'{i}):')
            for ecu in i:
                print(f'\tType: {ecu.type} | Year: {ecu.year} | ', end=None)
                print(f'Make: {ecu.make} | Model: {ecu.model}', end="\n\n")

    def __request_devices(self, requestedECUs: list):
        if self.broker.request_devices(requestedECUs):
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
        os.system('cls' if os.name == 'nt' else 'clear')
        term_size = shutil.get_terminal_size()
        greeting_message = "* ECU Selection Menu *"
        print(f'{tcolors.green}{greeting_message:*^{term_size[0]-5}}{tcolors.reset}')

    def __listen(self, timeout=None, waiting_msg = None) -> None:
        if waiting_msg:
            self.__typewritter(waiting_msg, tcolors.cyan)
        try:
            connection_events = self.sel.select(timeout=timeout)
            for key, mask in connection_events:
                self._key = key
                callback = key.data.callback
                callback(key)
        except TimeoutError:
            logging.error("Selector timed-out while waiting for a response or SSE.")
            return
        except KeyboardInterrupt:
            return

    def __parse_session_message(self, key: selectors.SelectorKey):
        key.fileobj.recv(4096)

    def send(self, control) -> None:
        message = self.frame.pack(control)
        self.socks["carla"].sendto(message, (self.mcast_ip, self.carla_port))

    def receive(self, control, verbose=False) -> None:
        try:
            data = self.socks["can"].recv(20)
            if len(data) == 20:  # 20 is size of carla struct in bytes
                ecm_data = struct.unpack("Ifff???B", data)
                if not self.frame(ecm_data, control, verbose):
                    self.__frame_miss_match(ecm_data, verbose)
        except socket.timeout:
            self.socks["can"].settimeout(0.04)
            self.dropped_messages += 1
            self.timeouts += 1
            print(f'Socket Timeout. Total: {self.timeouts}')

    def __frame_miss_match(self, ecm_data, verbose=False) -> None:
        self.dropped_messages += 1
        self.seq_miss_match += 1
        self.socks["can"].settimeout(0.01)
        for i in range(self.frame.last_frame - ecm_data[0]):
            self.socks["can"].recv(20)
            self.dropped_messages += 1
            self.seq_miss_match += 1
        self.socks["can"].settimeout(0.04)
        if verbose:
            print(ecm_data[0])
            print(self.frame.last_frame)
            print(
                f'Sequence number miss match. Total: {self.seq_miss_match}')

    def __set_mcast_options(self, mcast_grp, socks: SOCK_DICT) -> None:
        for key, sock in socks.items():
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
            sock.bind((mcast_grp, self[key + "_port"]))
            mreq = struct.pack("4sl", socket.inet_aton(mcast_grp),
                               socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP,
                            socket.IP_ADD_MEMBERSHIP, mreq)
            sock.settimeout(0.4)

    def __setup_sss3(self, _address: ADDR_LIST):
        source_addr = (self.__find_source_address(), _address[0][1])
        successfully_setup = []
        for address in _address:
            # Create Connection automatically tries all dns results for
            # hostname addresses on both IPv4 and IPv6.
            with socket.create_connection(address, 1, source_addr) as tcp_sock:
                tcp_sock.settimeout(1)
                if self.__send_setup(tcp_sock, address):
                    successfully_setup.append(address)
        return successfully_setup

    def __find_source_address(self) -> str:
        """
        If the host device is connected to multiple NICs then choose the one
        with the ip beginning in 192.168.X.X. If that IP does not exist then
        choose the first IP.
        """
        all_ip = re.compile(
            '([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})')
        local_subnet_ip = re.compile('192\.168\.([0-9]{1,3})\.([0-9]{1,3})')
        command = "ipconfig" if os.name == 'nt' else "ifconfig"
        all_ipconfig = all_ip.search(subprocess.check_output([command]))
        local_ipconfig = local_subnet_ip.search(
            subprocess.check_output([command]))
        if local_ipconfig:
            return local_ipconfig.group()
        else:
            return all_ipconfig.group()

    def __send_setup(self, tcp_sock: SOCK_T, address: ADDR_T, retry=True) -> bool:
        try:
            mcast_ip = socket.inet_aton(self.mcast_ip)
            mcast_packet_size = 20
            setup_message = struct.pack(
                "4sii", mcast_ip, self.carla_port, self.can_port, mcast_packet_size)
            tcp_sock.sendall(setup_message)
            confirmation = tcp_sock.recv(1)
            # True if sss3 setup correctly
            return struct.unpack("?", confirmation)[0]
        except (socket.herror, socket.gaierror, socket.timeout) as err:
            if retry:
                # DNS name assignment or socket closing may need to complete
                time.sleep(1)
                # Retry once
                return self.__send_setup(tcp_sock, address, False)
            else:
                print(f"Error: {err}")
                raise


if __name__ == '__main__':
    sss3object = SSS3()
