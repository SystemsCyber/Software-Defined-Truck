import atexit
import logging
from io import BytesIO
from HealthReport import NetworkStats
from SensorNode import SensorNode, Member_Node, COMMBlock
from HTTPClient import HTTPClient
from typing import List, NamedTuple, Type
from types import SimpleNamespace
from time import time, sleep
from pprint import pprint
from socket import *
from selectors import *
from threading import Thread
from TypeWriter import TypeWriter as tw
from ctypes import *
from pandas import DataFrame

class Controller(SensorNode, HTTPClient):
    def __init__(self, _max_retrans = 3, _max_frame_rate = 60, _server_ip = gethostname()) -> None:
        super().__init__(
            _max_retrans = _max_retrans,
            _max_frame_rate = _max_frame_rate,
            _server_ip = _server_ip
            )
        atexit.register(self.shutdown)
        
        self.read_length = sizeof(COMMBlock)
        self.l_thread = Thread(target=self.__listen, args=(self.timeout_additive,))
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
                self.check_members()
            except TimeoutError:
                self.check_members()
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
            with BytesIO(self.response_data) as self.rfile:
                self.do_POST()

    def do_POST(self):  # Equivalent of start
        try:
            ip, port, request_data = super().do_POST()
            if ip:
                tw.write("Received session information:", tw.magenta)
                pprint(request_data)
                self.start_session(ip, port, request_data)
                self.network_stats = NetworkStats(len(self.members))
                tw.write("Starting the session!", tw.yellow)
                if self.l_thread.is_alive():
                    self.listen = False
                    self.l_thread.join(1)
                self.listen = True
                self.l_thread.start()
            else:
                tw.write("Did not receive session information.", tw.magenta)
                tw.write("Exiting...", tw.red)
        except TypeError as te:
            logging.error(te)

    def do_DELETE(self):  # Equivalent of stop
        tw.write("Stopping session.", tw.red)
        super().do_DELETE()
        self.stop_session()

    def write(self, *key) -> None:
        if isinstance(key[0], SelectorKey):
            super().write(key[0].data.message)
            key[0].data.callback = self.read
            self.sel.modify(key[0].fileobj, EVENT_READ, key[0].data)
        elif self.session_status == self.SessionStatus.Active:
            self.can_key.data.callback = self.write
            self.can_key.data.message = self.packSensorData(*key)
            with self.sel_lock:
                self.sel.modify(self.can_key.fileobj, EVENT_WRITE, self.can_key.data)

    def read(self, key: SelectorKey) -> None:
        msg, buffer = super().read()
        if msg:
            print(msg)
            if msg.type == 1:
                self.network_stats.update(msg)
            elif msg.type == 4:
                pass
                # for row in self.health_report.columns()
            
    def shutdown(self, notify_server = True):
        self.do_DELETE()
        super().shutdown(notify_server)
        if self.l_thread.is_alive():
            self.listen = False
            self.l_thread.join(1)
    
    def __update_health_view(self):
        pass



if __name__ == '__main__':
    controller = Controller(10)
    controller.setup()