import atexit
import logging
from NetworkStats import NetworkStats
from SensorNode import SensorNode
from HTTPClient import HTTPClient
from typing import List
from types import SimpleNamespace
from time import time, sleep
from pprint import pprint
from socket import *
from selectors import *
from threading import Thread
from TypeWriter import TypeWriter as tw
from Frame import CAN_UDP_Frame

class Controller(SensorNode, HTTPClient):
    def __init__(self, _max_retrans: int, _server_ip = gethostname()) -> None:
        SensorNode.__init__(_max_retrans)
        HTTPClient.__init__(_server_ip)
        atexit.register(self.shutdown)
        self.last_print_time = time()
        self.devices = {}
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

    def __provision_devices(self) -> bool:
        requested = self.__request_available_devices()
        if requested:
            for i in requested:
                self.devices[str(i)] = NetworkStats(i)
            data = SimpleNamespace(
                    callback = self.receive_SSE,
                    outgoing_message = None
                    )
            self.sel.modify(self.ctrl.sock, EVENT_READ, data)
            return True
        return False

    def setup(self):
        if self.connect() and self.register():
            if self.__provision_devices():
                self.do_POST()
            else:
                tw.write("Exiting", tw.red)
                self.do_DELETE()

    def do_POST(self):
        try:
            super().do_POST()
        except SyntaxError as se:
            logging.error(se)
        else:
            tw.write((
                "Received session setup information "
                "from the server."
            ), tw.magenta)
            tw.write("Starting the session!", tw.yellow)
            self.start_session()
            can_data = SimpleNamespace(
                callback = self.read,
                outgoing_message = None
                )
            self.key = self.sel.register(self.can_sock, EVENT_READ, can_data)
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

    def do_DELETE(self):
        tw.write("Stopping session.", tw.red)
        self.listen = False
        self.devices = {}
        self.send_delete("/client/session")
        self.sel.unregister(self.can_sock)
        self.stop_session()

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
                self.last_frame_sent_time = current_time
                key.data.callback = self.read
                key.data.outgoing_message = None
                self.sel.modify(key.fileobj, EVENT_READ, key.data)
            except InterruptedError:
                logging.error("Message was interrupted while sending.")
            except BlockingIOError:
                logging.error("Socket is currently blocked and cannot send messages.")
        else:
            with self.sel_lock:
                self.key.data.callback = self.write
                self.key.data.outgoing_message = key
                self.sel.modify(self.key.fileobj, EVENT_WRITE, self.key.data)

    def __print_stats(self, current_time: float):
        if current_time - self.last_print_time > 1:
            self.last_print_time = current_time
            for device in self.devices.values():
                print(device)

    def __process_can_frame(self, can_frame: CAN_UDP_Frame, verbose = False) -> None:
        current_time = time()
        id = str(can_frame.device_id)
        if id in self.devices.keys():
            self.devices[id].last_can_message_time = current_time
            self.devices[id].calculate_stats(can_frame, self.last_frame, self.last_frame_sent_time)
            if verbose: self.__print_stats(current_time)
        else:
            logging.error("Received a CAN frame from an out-of-band device.")

    def read(self, key: SelectorKey) -> None:
        try:
            data = super().read()
        except timeout:
            logging.warning(f'Socket timed out.')
        except OSError as oe:
            logging.error(oe)
        else:
            self.__process_can_frame(data)

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