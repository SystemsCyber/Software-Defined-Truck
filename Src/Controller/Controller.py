import logging
import selectors as sel
from io import BytesIO
from multiprocessing import Event, current_process
from multiprocessing.connection import Client, Connection
from pprint import pprint
from time import time
from types import SimpleNamespace
from typing import List

from HealthReport import HealthReport, NetworkStats
from HTTPClient import HTTPClient
from SensorNode import COMMBlock, SensorNode, WCOMMFrame
from Text import TypeWriter as tw


class Controller(SensorNode, HTTPClient):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_request = time()

    def __request_health(self, now: float) -> None:
        if (now - self._last_request) >= 1.0:
            self._last_request = now
            msg = COMMBlock(self.index, self.frame_number,
                            int(now * 1000), 3, WCOMMFrame())
            for i in range(len(self.members)):
                    print(self.network_stats.health_report[i])
            self.health_report.update(
                self.index, self.network_stats.health_report)
            self.network_stats.reset()
            self.can_key.data.callback = self.write
            self.can_key.data.message = bytes(msg)
            self.sel.modify(self.can_key.fileobj,
                            sel.EVENT_WRITE, self.can_key.data)

    def __write_signals(self, key: sel.SelectorKey) -> None:
        try:
            signals = key.fileobj.recv()
            if signals:
                self.write(*signals)
            else:
                logging.debug("IPC sockets closed.")
        except EOFError as ee:
            logging.debug(ee)
            logging.debug("IPC sockets closed.")

    def __listen(self, running: Event) -> None:
        while running.is_set() and not self.close_connection:
            connection_events = self.sel.select(timeout=self.timeout_additive)
            for key, mask in connection_events:
                callback = key.data.callback
                callback(key)
            now = time()
            self.check_members(now)
            self.__request_health(now)

    def __request_devices(self, req: list, devices: list, conn: Connection) -> List[int]:
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
            return self.__request_available_devices(conn)

    def __print_devices(self, available_devices: list, conn: Connection) -> List[int]:
        tw.bar()
        tw.write("Available ECUs: ", tw.magenta)
        pprint(available_devices)
        tw.write((
            "Enter the numbers corresponding to the ECUs you "
            "would like to use (comma separated): "
        ), tw.magenta, end=None)
        conn.send("ask")
        input_list = str(conn.recv()).split(',')
        return [int(i.strip()) for i in input_list]

    def __request_user_input(self, available: list, conn: Connection) -> List[int]:
        available_device_ids = [device["ID"] for device in available]
        requested = self.__print_devices(available, conn)
        if set(requested).issubset(available_device_ids):
            return self.__request_devices(requested, available, conn)
        else:
            tw.write((
                "One or more numbers entered do not correspond"
                " with the available devices."
            ), tw.red)
            return self.__request_user_input(available)

    def __request_available_devices(self, conn: Connection) -> List[int]:
        available_devices = self.get_devices()
        if len(available_devices) > 0:
            return self.__request_user_input(available_devices, conn)
        else:
            tw.bar()
            tw.write((
                "Unfortunately, there are no available ECUs "
                "right now. Please check back later."
            ), tw.red)
            return []

    def __provision_devices(self, conn: Connection, running: Event) -> None:
        requested = self.__request_available_devices(conn)
        conn.send("break")
        if requested:
            data = SimpleNamespace(
                callback=self.receive_SSE, outgoing_message=None)
            self.sel.modify(self.ctrl.sock, sel.EVENT_READ, data)
            with BytesIO(self.response_data) as self.rfile:
                self.do_POST()
            self.__listen(running)
        else:
            tw.write("Exiting", tw.red)

    def start(self, port: int, running: Event) -> None:
        authkey = current_process().authkey
        conn = Client(('localhost', port), authkey=authkey)
        data = SimpleNamespace(callback=self.__write_signals)
        self.sel.register(conn, sel.EVENT_READ, data)
        if self.connect() and self.register():
            self.__provision_devices(conn, running)
            self.stop(ipc_conn=conn)

    def do_POST(self):  # Equivalent of start
        try:
            ip, port, request_data = super().do_POST()
            if ip:
                tw.write("Received session information:", tw.magenta)
                pprint(request_data)
                self.start_session(ip, port, request_data)
                self.network_stats = NetworkStats(len(self.members))
                self.health_report = HealthReport(len(self.members))
                self._last_request = time() + 5  # Give it a few secs for carla to start
                tw.write("Starting the session!", tw.yellow)
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
        if isinstance(key[0], sel.SelectorKey):
            super().write(key[0].data.message)
            key[0].data.callback = self.read
            self.sel.modify(key[0].fileobj, sel.EVENT_READ, key[0].data)
        elif self.session_status == self.SessionStatus.Active:
            self.can_key.data.callback = self.write
            self.can_key.data.message = self.packSensorData(*key)
            self.sel.modify(self.can_key.fileobj,
                            sel.EVENT_WRITE, self.can_key.data)

    def read(self, key: sel.SelectorKey) -> None:
        msg, buffer = super().read()
        if msg:
            if msg.type == 1:
                self.network_stats.update(
                    msg.index,
                    len(buffer),
                    msg.timestamp,
                    msg.frame.canFrame.sequence_number
                )
            elif msg.type == 4:
                report = self.health_report.report.from_buffer_copy(
                    buffer, self.comm_head_size
                )
                for i in range(len(self.members)):
                    print(report[i])
                self.health_report.update(msg.index, report)

    def stop(self, ipc_conn=None, notify_server=True):
        if ipc_conn:
            self.sel.unregister(ipc_conn)
        self.do_DELETE()
        super().shutdown(notify_server)
        self.sel.close()
