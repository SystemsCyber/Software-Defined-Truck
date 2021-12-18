import atexit
import logging
from NetworkStats import NetworkStats
from CANNode import WCANBlock
from SensorNode import SensorNode, WSenseBlock
from HTTPClient import HTTPClient
from typing import List, NamedTuple
from types import SimpleNamespace
from time import time, sleep
from pprint import pprint
from socket import *
from selectors import *
from threading import Thread
from TypeWriter import TypeWriter as tw
from ctypes import *
from pandas import DataFrame


class WCOMMFrame(Union):
    _fields_ = [
        ("can", WCANBlock),
        ("signals", WSenseBlock)
    ]

class COMMBlock(Structure):
    _fields_ = [
        ("id", c_uint32),
        ("frame_number", c_uint32),
        ("timestamp", c_uint32),
        ("type", c_uint8),
        ("frame", WCOMMFrame)
    ]

    def __repr__(self) -> str:
        s =  (
            f'Device: {self.id} Frame Number: {self.frame_number}\n'
            f'Timestamp: {self.timestamp} Type: {self.type}\n'
        )
        if self.type == 1:
            s += f'Frame:\n{self.frame.can}\n'
        elif self.type == 2:
            s += f'Frame:\n{self.frame.signals}\n'
        return s

class Controller(SensorNode, HTTPClient):
    def __init__(self, _max_retrans = 3, _max_frame_rate = 60, _server_ip = gethostname()) -> None:
        SensorNode.__init__()
        HTTPClient.__init__(_server_ip)
        atexit.register(self.shutdown)
        self.id = None
        self.members = {}
        self.max_retransmissions = _max_retrans
        self.attempts = 0
        self.max_frame_rate = _max_frame_rate
        self.timeout = (1/self.max_frame_rate) * (_max_retrans)
        self.read_length = len(COMMBlock)
        self.frame_number = 1
        self.l_thread = Thread(target=self.__listen, args=(self.timeout,))
        self.l_thread.setDaemon(True)
        self.listen = True

    def __listen(self, _timeout=None) -> None:
        while self.listen:
            try:
                with self.sel_lock:
                    connection_events = self.sel.select(timeout=_timeout)
                    for key, mask in connection_events:
                        callback = key.data.callback
                        callback(key)
                self.__check_connections()
            except TimeoutError:
                continue
            except KeyboardInterrupt:
                return

    def __request_devices(self, req: list, devices: list) -> List[int]:
        if self.request_devices(req, devices):
            tw.write((
                "Requested devices were successfully allocated."
            ), tw.yellow)
            return req
        else:
            tw.write((
                "One or more of the requested devices are no "
                "longer available. Please select new device(s)."
            ), tw.red)
            return self.__request_available_devices()

    def __print_devices(self, available_devices: list) -> List[int]:
        tw.bar()
        tw.write("Available ECUs: ", tw.magenta)
        pprint(available_devices)
        tw.write((
            "Enter the numbers corresponding to the ECUs you "
            "would like to use (comma separated): "
        ), tw.magenta, end=None)
        input_list = input('').split(',')
        return [int(i.strip()) for i in input_list]

    def __request_user_input(self, available: list) -> List[int]:
        available_device_ids = [device["ID"] for device in available]
        requested = self.__print_devices(available)
        if set(requested).issubset(available_device_ids):
            return self.__request_devices(requested, available)
        else:
            tw.write((
                "One or more numbers entered do not correspond"
                " with the available devices."
            ), tw.red)
            return self.__request_user_input(available)

    def __request_available_devices(self) -> List[int]:
        available_devices = self.get_devices()
        if len(available_devices) > 0:
            return self.__request_user_input(available_devices)
        else:
            tw.bar()
            tw.write((
                "Unfortunately, there are no available ECUs "
                "right now. Please check back later."
            ), tw.red)
            return []

    def __provision_devices(self):
        requested = self.__request_available_devices()
        if requested:
            data = SimpleNamespace(
                    callback = self.receive_SSE,
                    outgoing_message = None
                    )
            self.sel.modify(self.ctrl.sock, EVENT_READ, data)
        else:
            tw.write("Exiting", tw.red)

    def setup(self):
        if self.connect() and self.register():
            self.__provision_devices()

    def do_POST(self):  # Equivalent of start
        super().do_POST()
        self.id = self.request_data["ID"]
        for i in self.request_data["MEMBERS"]:
            self.members[int(i)] = SimpleNamespace(
                last_received_frame = 0,
                health_report = None
            )
        l = len(self.members)
        k = self.members.keys()
        self.network_stats = NetworkStats(self.id, k)
        self.health_report = {
            
        }
        tw.write((
            "Received session setup information "
            "from the server."
        ), tw.magenta)
        tw.write("Starting the session!", tw.yellow)
        if self.l_thread.is_alive():
            self.listen = False
            self.l_thread.join(1)
            self.listen = True
            self.l_thread.start()
        else:
            self.listen = True
            self.l_thread.start()
            # control = SimpleNamespace(throttle = 1.0, steer = 1.0, brake = 1.0, hand_brake = 1, reverse = 1,manual_gear_shift = 1, gear = 1)
            # try:
            #     while True:
            #         self.write(control)
            #         sleep(1)
            # except KeyboardInterrupt:
            #     pass

    def do_DELETE(self):  # Equivalent of stop
        tw.write("Stopping session.", tw.red)
        self.listen = False
        self.id = None
        self.members = {}
        return super().do_DELETE()

    def write(self, key) -> None:
        if isinstance(key, SelectorKey):
            try:
                super().write(key.data.outgoing_message)
                key.data.timeout = time() + self.timeout
                key.data.callback = self.read
                self.sel.modify(key.fileobj, EVENT_READ, key.data)
            except InterruptedError:
                logging.error("Message was interrupted while sending.")
            except BlockingIOError:
                logging.error("Socket is currently blocked and cannot send messages.")
        else:
            self.can_key.data.callback = self.write
            self.can_key.data.outgoing_message = key
            self.attempts = 0
            self.frame_number += 1
            with self.sel_lock:
                self.sel.modify(self.can_key.fileobj, EVENT_WRITE, self.can_key.data)

    def __process_message(self, msg: COMMBlock, msg_size: int) -> None:
        device = self.members[msg.id]
        device.last_received_frame = msg.frame_number
        if msg.type == 1:
            self.network_stats.update(msg, msg_size)
        elif msg.type == 4:
            pass
            # for row in self.health_report.columns()

    def read(self, key: SelectorKey) -> None:
        try:
            # TODO: Read length for health messages will be longer than current COMMBlock size.
            buffer = super().read(self.read_length)
            self.__process_message(COMMBlock.from_buffer_copy(buffer), len(buffer))
        except timeout:
            logging.warning(f'Socket timed out.')
        except OSError as oe:
            logging.error(oe)
        except (AttributeError, ValueError) as ae:
            logging.error("Received data from an out of band device.")
            logging.error(ae)
            
    def shutdown(self, notify_server = True):
        self.do_DELETE()
        super().shutdown(notify_server)
        self.l_thread.join(1)

    def __retransmit(self, id: int):
        if self.attempts < self.max_retransmissions:
            self.attempts += 1
            with self.sel_lock:
                self.sel.modify(self.can_key.fileobj, EVENT_WRITE, self.can_key.data)
        elif self.attempts == self.max_retransmissions:
            logging.error(
                f"Have not received frame #{self.frame_number} "
                f"from device {id} after "
                f"{self.max_retransmissions} attempts."
                )
            self.attempts += 1
    
    def __check_connections(self):
        now = time()
        for k,v in self.members.items():
            not_recv_frame = v.last_received_frame != self.frame_number
            timedout = now >= v.timeout
            if not_recv_frame and timedout:
                self.__retransmit(k)
                break
    
    def __update_health_view(self):
        pass



if __name__ == '__main__':
    controller = Controller(10)
    controller.setup()