import atexit
import logging
from NetworkStats import NetworkStats
from CANNode import WCANBlock
from SensorNode import SensorNode, WSenseBlock
from HTTPClient import HTTPClient
from typing import List
from types import SimpleNamespace
from time import time, sleep
from pprint import pprint
from socket import *
from selectors import *
from threading import Thread
from TypeWriter import TypeWriter as tw
from ctypes import *


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
    def __init__(self, _max_retrans: int, _server_ip = gethostname()) -> None:
        SensorNode.__init__(_max_retrans)
        HTTPClient.__init__(_server_ip)
        atexit.register(self.shutdown)
        self.id = None
        self.members = None
        self.l_thread = Thread(target=self.__listen, args=(0,))
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
                    # self.__check_connection()
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

    def do_POST(self):
        super().do_POST()
        self.id = self.request_data["ID"]
        self.members = self.request_data["MEMBERS"]
        self.network_stats = NetworkStats(self.id, self.members)
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

    def do_DELETE(self):
        tw.write("Stopping session.", tw.red)
        self.listen = False
        self.id = None
        self.members = list
        return super().do_DELETE()

    def write(self, key) -> None:
        if isinstance(key, SelectorKey):
            try:
                super().write(key.data.outgoing_message)
                current_time = time()
                # timepassed = current_time - self.last_frame_sent_time
                # new_rate = 1 / timepassed
                # new_rate -= self.avg_sending_rate
                # self.avg_sending_rate += ((new_rate) / self.frame.last_frame)
                # self.retrans_timeout = 1 / (self.max_retrans * self.avg_sending_rate)
                self.last_transmission_time = current_time
                key.data.callback = self.read
                key.data.outgoing_message = None
                self.sel.modify(key.fileobj, EVENT_READ, key.data)
            except InterruptedError:
                logging.error("Message was interrupted while sending.")
            except BlockingIOError:
                logging.error("Socket is currently blocked and cannot send messages.")
        else:
            with self.sel_lock:
                key = self.sel.get_key(self.can_sock)
                key.data.callback = self.write
                key.data.outgoing_message = key
                self.sel.modify(key.fileobj, EVENT_WRITE, key.data)

    def read(self, key: SelectorKey) -> None:
        try:
            data = COMMBlock.from_buffer_copy(super().read(len(COMMBlock)))
        except timeout:
            logging.warning(f'Socket timed out.')
        except OSError as oe:
            logging.error(oe)
        else:
            if data.id in self.members:
                if data.type == 1:
                    self.network_stats.update(
                        data.id,
                        len(COMMBlock),
                        data.timestamp,
                        data.sequence_number
                        )
                elif data.type == 4:
                    pass
            else:
                logging.error("Received data from an out of band device.")

    def shutdown(self, notify_server = True):
        self.do_DELETE()
        super().shutdown(notify_server)
        self.l_thread.join(1)
    
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