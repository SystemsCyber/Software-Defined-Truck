import logging
import selectors as sel
from io import BytesIO
from pprint import pprint
from threading import Event, Thread
from time import sleep, time
from types import SimpleNamespace
from typing import List
from multiprocessing import SimpleQueue

from HealthReport import HealthReport, NetworkStats
from HTTPClient import HTTPClient
from SensorNode import COMMBlock, SensorNode, WCOMMFrame
from Text import TypeWriter as tw


class Controller(SensorNode, HTTPClient):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def __request_health(self, _listen: Event) -> None:
        while _listen.is_set():
            sleep(1)
            msg = COMMBlock(
                self.index,
                self.frame_number,
                int(time() * 1000),
                3,
                WCOMMFrame()
            )
            self.network_stats.reset()
            self.can_key.data.callback = self.write
            self.can_key.data.message = bytes(msg)
            with self.sel_lock:
                self.sel.modify(self.can_key.fileobj,
                                sel.EVENT_WRITE, self.can_key.data)

    def __check_members(self, _listen: Event) -> None:
        while _listen.is_set():
            sleep(self.timeout_additive)
            super().check_members()

    def __write_signals(self, conn: SimpleQueue) -> None:
        while True:
            try:
                signals = conn.get()  # TODO this wont stop when the rest does
                self.write(*signals)
            except EOFError:
                return

    def __listen(self, _listen: Event) -> None:
        while _listen.is_set():
            try:
                with self.sel_lock:
                    connection_events = self.sel.select(timeout=1)  # Decreasing the timeout increases the message rate which means that threads are not switching when they hit this line.
                for key, mask in connection_events:
                    callback = key.data.callback
                    callback(key)
            except KeyboardInterrupt:
                return

    def __request_devices(self, req: list, devices: list, conn: SimpleQueue) -> List[int]:
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

    def __print_devices(self, available_devices: list, conn: SimpleQueue) -> List[int]:
        tw.bar()
        tw.write("Available ECUs: ", tw.magenta)
        pprint(available_devices)
        tw.write((
            "Enter the numbers corresponding to the ECUs you "
            "would like to use (comma separated): "
        ), tw.magenta, end=None)
        conn.put("ask")
        input_list = str(conn.get()).split(',')
        return [int(i.strip()) for i in input_list]

    def __request_user_input(self, available: list, conn: SimpleQueue) -> List[int]:
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

    def __request_available_devices(self, conn: SimpleQueue) -> List[int]:
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

    def __provision_devices(self, conn: SimpleQueue):
        requested = self.__request_available_devices(conn)
        conn.put("break")
        if requested:
            data = SimpleNamespace(
                callback=self.receive_SSE,
                outgoing_message=None
            )
            self.sel.modify(self.ctrl.sock, sel.EVENT_READ, data)
        else:
            tw.write("Exiting", tw.red)

    def start(self, conn: SimpleQueue, listen: Event) -> None:
        if self.connect() and self.register():
            self.__provision_devices(conn)
            with BytesIO(self.response_data) as self.rfile:
                self.do_POST()
            signal_thd = Thread(target=self.__write_signals, args=(conn,))
            report_thd = Thread(target=self.__request_health, args=(listen,))
            check_thd = Thread(target=self.__check_members, args=(listen,))
            signal_thd.start()
            report_thd.start()
            if self.max_retransmissions > 0:
                check_thd.start()
            self.__listen(listen)
            signal_thd.join(1)
            report_thd.join(1)
            if self.max_retransmissions > 0:
                check_thd.join(1)
            self.stop()

    def do_POST(self):  # Equivalent of start
        try:
            ip, port, request_data = super().do_POST()
            if ip:
                tw.write("Received session information:", tw.magenta)
                pprint(request_data)
                self.start_session(ip, port, request_data)
                self.network_stats = NetworkStats(len(self.members))
                self.health_report = HealthReport(len(self.members))
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
            with self.sel_lock:
                self.sel.modify(self.can_key.fileobj,
                                sel.EVENT_WRITE, self.can_key.data)

    def read(self, key: sel.SelectorKey) -> None:
        msg, buffer = super().read()
        if msg:
            print(msg)
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
                # for i in range(len(self.members)):
                #     print(report[i])
                self.health_report.update(msg.index, report)
                # print(self.health_report.packet_loss)
                # print(self.health_report.latency)
                # print(self.health_report.jitter)
                # print(self.health_report.goodput)

    def stop(self, notify_server=True):
        print("Times socket blocked: ", self.socket_blocked)
        print("Times messages recvd: ", self.messages_recvd)
        self.do_DELETE()
        super().shutdown(notify_server)
