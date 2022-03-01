import logging
import selectors as sel
from io import BytesIO
from logging.handlers import QueueHandler
from multiprocessing import Event, Queue, current_process
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
        self._just_packed_frame = False

    def __request_health(self, now: float) -> None:
        if (now - self._last_request) >= 1.0:
            self._last_request = now
            msg = COMMBlock(self.index, self.frame_number,
                            int(now * 1000), 3, WCOMMFrame())
            self.health_report.update(
                self.index, self.network_stats.health_report, self.frame_number)
            self._health_queue.put(
                SimpleNamespace(
                    sim_frames=self.health_report.sim_frames,
                    can_frames=self.health_report.can_frames,
                    dropped_sim_frames=self.health_report.dropped_sim_frames,
                    dropped_can_frames=self.health_report.dropped_can_frames,
                    packet_loss=self.health_report.packet_loss,
                    latency=self.health_report.latency,
                    jitter=self.health_report.jitter,
                    goodput=self.health_report.goodput
                ))
            self.network_stats.reset()
            self.can_key.data.callback = self.write
            self.can_key.data.message = bytes(msg)
            self.sel.modify(self.can_key.fileobj,
                            sel.EVENT_WRITE, self.can_key.data)
    
    def __first_ntp_sync(self) -> None:
        logging.info("Synchronizing with the NTP server for the first time.")
        logging.info("This takes several seconds.")
        end_sync = time() + 14
        while(end_sync > time()):
            connection_events = self.sel.select(timeout=0.5)
            for key, mask in connection_events:
                callback = key.data.callback
                callback(key)
            self.time_client.update(time())

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
            connection_events = self.sel.select(timeout=0.001)
            for key, mask in connection_events:
                callback = key.data.callback
                callback(key)
            if self._just_packed_frame:
                self._just_packed_frame = False
            else:
                now = time()
                self.check_members(now)
                self.__request_health(now)
                self.time_client.update(now)

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
            return self.__request_user_input(available, conn)

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
        self.__first_ntp_sync()
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

    def start(
            self,
            port: int,
            running: Event,
            log_queue: Queue,
            health_queue: Queue,
            log_level=logging.DEBUG
            ) -> None:
        root = logging.getLogger()
        root.addHandler(QueueHandler(log_queue))
        root.setLevel(log_level)
        self._health_queue = health_queue
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
                self.network_stats = NetworkStats(len(self.members), self.time_client)
                self.health_report = HealthReport(self.members)
                self._last_request = time() + 10  # Time to sync with NTP server
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
            self._just_packed_frame = True

    def __read_type_1(self, msg: COMMBlock, buffer: bytes) -> None:
        self.network_stats.update(
            msg.index,
            len(buffer),
            msg.timestamp,
            msg.frame.canFrame.sequence_number
        )
        if int(msg.frame.canFrame.frame.can.can_id) == int(0x18F00300 ^ 0x1FFFFFFF):
            print(f"CAN ID: {hex(msg.frame.canFrame.frame.can.can_id ^ 0x1FFFFFFF)}", end=" ")
            for i in range(msg.frame.canFrame.frame.can.len):
                end = "\n" if i == 7 else " "
                print(msg.frame.canFrame.frame.can.buf[i], end=end)

    def __read_type_4(self, msg: COMMBlock, buffer: bytes) -> None:
        report = self.health_report.report.from_buffer_copy(
            buffer, self.comm_head_size)
        self.health_report.update(
            msg.index,
            report,
            self.members[msg.index].last_seq_num
            )

    def read(self, key: sel.SelectorKey) -> None:
        msg, buffer = super().read()
        if msg and msg.type == 1:
            self.__read_type_1(msg, buffer)
        elif msg and msg.type == 4:
            self.__read_type_4(msg, buffer)

    def stop(self, ipc_conn=None, notify_server=True):
        logging.info(f"Simulator Frame Retransmissions: {self.times_retrans}")
        if ipc_conn:
            self.sel.unregister(ipc_conn)
        self.do_DELETE()
        super().shutdown(notify_server)
        self.sel.close()
