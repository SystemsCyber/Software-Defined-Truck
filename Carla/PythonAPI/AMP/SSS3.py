import socket
import struct
import sys
import time
import atexit
import selectors
from typing import Union, Tuple, List, Dict, Optional
from frame import Frame
from types import SimpleNamespace
import logging
from logging.handlers import TimedRotatingFileHandler
from HelperMethods import ColoredConsoleHandler, LogFolder
from BrokerHandle import BrokerHandle
import shutil
from ipaddress import IPv4Address
# import multiprocessing as mp
import threading
from collections import namedtuple

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
        atexit.register(self.shutdown)
        self.__setup_logging()
        self.frame = Frame()
        self.last_frame_sent_time = time.time()
        self.devices = {}
        self.device = namedtuple("device", [
            "latency",
            "number_of_messages_received",
            "last_can_seq_number"
            "dropped_can_frames",
            "dropped_carla_frames" 
            ])
        self.sel = selectors.DefaultSelector()
        self.selector_lock = threading.Lock()
        self.broker = BrokerHandle(self.sel, self.selector_lock, _server_address)
        self.can = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.can.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.carla = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.carla.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.l_thread = threading.Thread(target=self.__listen, args=(0,))
        self.l_thread.setDaemon(True)
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
        filename = LogFolder.findpath("sss3_log")
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
            self.__request_devices(devices)
            data = SimpleNamespace(
                callback = self.__receive_SSE,
                outgoing_message = None
                )
            self.sel.modify(self.broker.ctrl.sock, selectors.EVENT_READ, data)
            self.start(self.broker.mcast_IP, self.broker.can_port)
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

    def __request_devices(self, devices: list):
        self.__print_devices(devices)
        available_device_ids = [device["ID"] for device in devices]
        requestedECUs = self.__request_user_select_devices(available_device_ids)
        if self.broker.request_devices(requestedECUs, devices):
            for i in requestedECUs:
                self.devices[str(i)] = self.device(0.0,0,0,0,0)
            self.__typewritter("Requested devices were successfully allocated.", tcolors.yellow)
        else:
            self.devices = {}
            self.__typewritter("One or more of the requested devices are no longer available. Please select new device(s).", tcolors.red)
            self.__select_devices(self.broker.get_devices())

    def __request_user_select_devices(self, device_ids: list) -> List:
        self.__typewritter("Enter the numbers corresponding to the ECUs you would like to use (comma separated): ", tcolors.magenta, end=None)
        input_list = input('').split(',')
        requestedECUs = [int(i.strip()) for i in input_list]
        if set(requestedECUs).issubset(device_ids):
            return requestedECUs
        else:
            self.__typewritter("One or more numbers entered do not correspond with the available devices.", tcolors.red)
            return self.__request_user_select_devices(device_ids)

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
                self.start(self.broker.mcast_IP, self.broker.can_port)
            elif self.broker.command.lower() == "delete":
                self.stop()

    def start(self, mcast_IP: IPv4Address, can_port: int):
        self.__typewritter("Received session setup information from the server.", tcolors.magenta)
        self.__typewritter("Starting the session!", tcolors.yellow)
        device_address = socket.gethostbyname_ex(socket.gethostname())[2][3]
        logging.info(device_address + " was chosen as the interface to subscribe to for multicast messages.")
        group = socket.inet_aton(str(mcast_IP))
        iface = socket.inet_aton(device_address)
        self.mreq = group + iface
        self.__set_mcast_options(can_port, iface)
        if self.l_thread.is_alive():
            self.listen = False
            self.l_thread.join(1)
            self.listen = True
            self.l_thread.start()
        else:
            self.listen = True
            self.l_thread.start()
            control = SimpleNamespace(
                throttle = 1.0,
                steer = 1.0,
                brake = 1.0,
                hand_brake = 1,
                reverse = 1,
                manual_gear_shift = 1,
                gear = 1
            )
            try:
                while True:
                    self.send_control_frame(control)
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
                
    def __set_mcast_options(self, can_port:int, iface: str) -> None:
        self.can.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, self.mreq)
        self.can.bind(('', can_port))
        self.can.setblocking(False)
        can_data = SimpleNamespace(callback = self.__receive)
        self.sel.register(self.can, selectors.EVENT_READ, can_data)
        self.carla.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 128)
        self.carla.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, iface)
        self.carla.setblocking(False)
        carla_data = SimpleNamespace(
            callback = self.__send,
            outgoing_message = None
            )
        self._key = self.sel.register(self.carla, selectors.EVENT_READ, carla_data)

    def shutdown(self):
        self.stop()
        self.broker.do_DELETE()
        self.broker.send_delete("/client/register", True)

    def stop(self):
        self.__typewritter("Stopping session.", tcolors.red)
        self.listen = False
        self.broker.send_delete("/client/session")
        logging.debug("Leaving Multicast Membership.")
        self.can.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, self.mreq)
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
            if self.frame.frame_num == 4294967296:
                self.frame.frame_num = 0
            else:
                self.frame.frame_num += 1
            self.last_control_frame = control
            message = self.frame.packControlFrame(control)
            self._key.data.outgoing_message = message
            self.sel.modify(self._key.fileobj, selectors.EVENT_WRITE, self._key.data)

    def __send(self, key: selectors.SelectorKey) -> None:
        try:
            message = key.data.outgoing_message
            key.fileobj.sendto(message, (str(self.broker.mcast_IP), self.broker.carla_port))
            self.last_frame_sent_time = time.time()
            self.sel.modify(key.fileobj, selectors.EVENT_READ, key.data)
        except InterruptedError:
            logging.error("Message was interrupted while sending.")
        except BlockingIOError:
            logging.error("Socket is currently blocked and cannot send messages.")

    def __receive(self, key: selectors.SelectorKey) -> None:
        try:
            data = key.fileobj.recv(36)
        except socket.timeout:
            logging.warning(f'Socket timed out.')
        except OSError as oe:
            logging.error(oe)
        else:
            if len(data) == 36:
                can_frame = self.frame.unpackCanFrame(data, verbose=True)
                self.__calc_device_stats(can_frame, True)

    def __calc_device_stats(self, can_frame, verbose=False) -> None:
        if not can_frame.device_id in self.devices.keys():
            logging.error("Received a CAN frame from an out-of-band device.")
            return
        current_device = self.devices[str(can_frame.device_id)]
        self.__calc_latency(current_device)
        self.__calc_dropped_frame(current_device, can_frame)
        if can_frame.sequence_number == 4294967296:
            current_device.last_can_seq_num = -1
        else:
            current_device.last_can_seq_num = can_frame.sequence_number
        if verbose: self.__print_stats()

    def __calc_latency(self, current_device):
        msg_rtt = time.time() - self.last_frame_sent_time
        curr_rtt = current_device.latency
        current_device.number_of_messages_received += 1
        curr_num = current_device.number_of_messages_received
        # From: https://stackoverflow.com/questions/22999487/update-the-average-of-a-continuous-sequence-of-numbers-in-constant-time
        current_device.latency += (msg_rtt - curr_rtt) / curr_num

    def __calc_dropped_frame(self, current_device, can_frame):
        frame_diff = self.frame.last_frame - can_frame.control_frame_ref
        seq_diff = can_frame.sequence_number - current_device.last_can_seq_num
        if frame_diff > 1:
            current_device.dropped_carla_frames += 1
        if seq_diff > 1:
            current_device.dropped_can_frames += 1

    def __print_stats(self):
        if hasattr(self, "last_print_time"):
            if time.time() - self.last_print_time > 1:
                for k,v in self.devices:
                    msg = (
                        f'[{k}]:\n'
                        f'\tLatency: {v.latency:>5.2f}ms\n'
                        f'\tDropped Carla Frames: {v.dropped_carla_frames}\n'
                        f'\tDropped CAN Frames: {v.dropped_can_frames}\n'
                    )
                    print(msg)
        else:
            self.last_print_time = time.time()


if __name__ == '__main__':
    sss3object = SSS3()
    sss3object.setup()
