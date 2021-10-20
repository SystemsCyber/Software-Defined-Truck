import atexit
import logging
from NetworkStats import NetworkStats
from CANNode import CANNode
from CANForwarder import CANForwarder
from HelperMethods import ColoredConsoleHandler, LogFolder, TypeWritter as tw
from ServerHandle import ServerHandle
from logging.handlers import TimedRotatingFileHandler
from typing import NamedTuple, List
from types import SimpleNamespace
from time import time, sleep
from pprint import pprint
from socket import *
from selectors import *
# import multiprocessing as mp
import threading


class Controller:
    """SSS3 communication utility in conjunction with the CARLA simulator"""

    def __init__(self, _max_retrans: int, _server_address = gethostname()) -> None:
        atexit.register(self.shutdown)
        self.__setup_logging()
        self.sel = DefaultSelector()
        self.selector_lock = threading.Lock()
        # self.selector_lock = mp.Lock()
        self.frame = CANForwarder()
        self.avg_sending_rate = 0
        self.last_frame_sent_time = time()
        self.last_print_time = time()
        self.max_retrans = _max_retrans
        self.retrans_timeout = 0
        self.devices = {}
        self.devices_keys = []
        self.broker = ServerHandle(self.sel, self.selector_lock, _server_address)
        # self.l_thread = threading.Thread(target=self.__listen, args=(0.01,))
        self.l_thread = threading.Thread(target=self.__listen, args=(0,))
        self.l_thread.setDaemon(True)
        # self.l_thread = mp.Process(target=self.__listen, args=(0.01, True))
        self.listen = True

    def __listen(self, _timeout=None) -> None:
        while self.listen:
            try:
                with self.selector_lock:
                    connection_events = self.sel.select(timeout=_timeout)
                    for key, mask in connection_events:
                        callback = key.data.callback
                        callback(key)
                    # self.__check_connection()
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

    def __request_devices(self, requested: list, devices: list) -> List[int]:
        if self.broker.request_devices(requested, devices):
            tw.write("Requested devices were successfully allocated.", tw.yellow)
            return requested
        else:
            tw.write("One or more of the requested devices are no longer available. Please select new device(s).", tw.red)
            return self.__request_available_devices()

    def __print_devices(self, available_devices: list) -> List[int]:
        tw.bar()
        tw.write("Available ECUs: ", tw.magenta)
        pprint(available_devices)
        tw.write("Enter the numbers corresponding to the ECUs you would like to use (comma separated): ", tw.magenta, end=None)
        input_list = input('').split(',')
        return [int(i.strip()) for i in input_list]

    def __request_user_input(self, available_devices: list) -> List[int]:
        available_device_ids = [dev["ID"] for dev in available_devices]
        requested = self.__print_devices(available_devices)
        if set(requested).issubset(available_device_ids):
            return self.__request_devices(requested, available_devices)
        else:
            tw.write("One or more numbers entered do not correspond with the available devices.", tw.red)
            return self.__request_user_input(available_devices)

    def __request_available_devices(self) -> List[int]:
        available_devices = self.broker.get_devices()
        if len(available_devices) > 0:
            return self.__request_user_input(available_devices)
        else:
            tw.bar()
            tw.write("Unfortunately, there are no available ECUs right now. Please check back later.", tw.red)
            return []

    def __provision_devices(self):
        requested = self.__request_available_devices()
        if requested:
            for i in requested:
                self.devices[str(i)] = NetworkStats(i)
            self.devices_keys = self.devices.keys()
            data = SimpleNamespace(
                    callback = self.__receive_SSE,
                    outgoing_message = None
                    )
            self.sel.modify(self.broker.ctrl.sock, EVENT_READ, data)
            self.start()
        else:
            tw.write("Exiting", tw.red)
            self.shutdown()

    def setup(self):
        if self.broker.connect():
            if self.broker.register():
                self.__provision_devices()
            else:
                logging.error("Request to register with server failed.")
        else:
            logging.error("Could not connect to the server.")
    
    def __receive_SSE(self, key: SelectorKey):
        try:
            self.broker.receive_SSE(key)
        except SyntaxError as se:
            logging.error(se)
        else:
            if self.broker.command.lower() == "post":
                self.start()
            elif self.broker.command.lower() == "delete":
                self.stop()

    def start(self):
        tw.write("Received session setup information from the server.", tw.magenta)
        tw.write("Starting the session!", tw.yellow)
        self.sss3 = CANNode(self.broker.mcast_IP, self.broker.can_port, self.broker.carla_port)
        can_data = SimpleNamespace(callback = self.__receive)
        self.sel.register(self.sss3.can, EVENT_READ, can_data)
        carla_data = SimpleNamespace(
            callback = self.__send,
            outgoing_message = None
            )
        self._key = self.sel.register(self.sss3.carla, EVENT_READ, carla_data)
        if self.l_thread.is_alive():
            self.listen = False
            self.l_thread.join(1)
            self.listen = True
            self.l_thread.start()
        else:
            self.listen = True
            self.l_thread.start()
            # control = SimpleNamespace(
            #     throttle = 1.0,
            #     steer = 1.0,
            #     brake = 1.0,
            #     hand_brake = 1,
            #     reverse = 1,
            #     manual_gear_shift = 1,
            #     gear = 1
            # )
            # try:
            #     while True:
            #         self.send_control_frame(control)
            #         sleep(1)
            # except KeyboardInterrupt:
            #     pass

    def shutdown(self):
        self.stop()
        self.broker.do_DELETE()
        self.broker.send_delete("/client/register", True)
        self.l_thread.join(1)

    def stop(self):
        tw.write("Stopping session.", tw.red)
        self.listen = False
        self.devices = {}
        self.devices_keys = []
        self.broker.send_delete("/client/session")
        if hasattr(self, "sss3"):
            self.sel.unregister(self.sss3.can)
            self.sel.unregister(self.sss3.carla)
            self.sss3.stop()

    def send_control_frame(self, control):
        if self.frame.frame_num == 4294967296:
            self.frame.frame_num = 0
        else:
            self.frame.frame_num += 1
        self.last_control_frame = control
        message = self.frame.packControlFrame(control)
        with self.selector_lock:
            self._key.data.outgoing_message = message
            self.sel.modify(self._key.fileobj, EVENT_WRITE, self._key.data)

    def __send(self, key: SelectorKey) -> None:
        try:
            self.sss3.send_carla_frame(key.data.outgoing_message)
            current_time = time()
            # timepassed = current_time - self.last_frame_sent_time
            # new_rate = 1 / timepassed
            # new_rate -= self.avg_sending_rate
            # self.avg_sending_rate += ((new_rate) / self.frame.last_frame)
            # self.retrans_timeout = 1 / (self.max_retrans * self.avg_sending_rate)
            self.last_frame_sent_time = current_time
            self.sel.modify(key.fileobj, EVENT_READ, key.data)
        except InterruptedError:
            logging.error("Message was interrupted while sending.")
        except BlockingIOError:
            logging.error("Socket is currently blocked and cannot send messages.")

    def __receive(self, key: SelectorKey) -> None:
        try:
            data = self.sss3.receive_can_messages()
        except timeout:
            logging.warning(f'Socket timed out.')
        except OSError as oe:
            logging.error(oe)
        else:
            if len(data) == 36:
                can_frame = self.frame.unpackCanFrame(data, True)
                self.__process_can_frame(can_frame)

    def __process_can_frame(self, can_frame: NamedTuple, verbose = False) -> None:
        current_time = time()
        id = str(can_frame.device_id)
        if id in self.devices_keys:
            self.devices[id].last_can_message_time = current_time
            self.devices[id].calculate_stats(can_frame, self.frame.last_frame, self.last_frame_sent_time)
            if verbose: self.__print_stats(current_time)
        else:
            logging.error("Received a CAN frame from an out-of-band device.")

    def __print_stats(self, current_time: float):
        if current_time - self.last_print_time > 1:
            self.last_print_time = current_time
            for device in self.devices.values():
                print(device)

    # def __check_connection(self):
    #     for device in self.devices:
    #         if device.last_frame_number < self.frame.last_frame:
    #             self.__retransmit_if_needed()
    #         if time() - device.last_can_message_time() > 1:
    #             logging.warning(f'[{device.id}] hasnt sent can messages in at least 1 second!')
            
    # def __retransmit_if_needed(self):
    #     if (time() - self.last_frame_sent_time) > self.retrans_timeout:
    #         self.send_control_frame(self.last_control_frame)


if __name__ == '__main__':
    controller = Controller(10)
    controller.setup()