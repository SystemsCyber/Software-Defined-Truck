from __future__ import annotations

import ctypes as ct
import logging
import multiprocessing as mp
import selectors as sel
import threading as th
from ipaddress import IPv4Address
from queue import Full
from time import sleep

from .CANNode import CAN_message, Member_Node, WCANBlock
from .Environment import OutputType as OT
from .HealthReport import HealthReport, NetworkStats, NodeReport
from .HTTPClient import HTTPClient
from .SensorNode import SensorNode, WSenseBlock

COM_PACKED_HEAD_SIZE = 14


class WCOMMFrame(ct.Union):
    _fields_ = [
        ("canFrame", WCANBlock),
        ("sensorFrame", WSenseBlock),
        ("healthFrame", ct.POINTER(NodeReport)),
        ("timeFrame", ct.c_uint64)
    ]


class COMMBlock(ct.Structure):
    _anonymous_ = ("frame",)
    _pack_ = 4
    _fields_ = [
        ("index", ct.c_uint32),
        ("frame_number", ct.c_uint32),
        ("timestamp", ct.c_uint64),
        ("type", ct.c_uint8),
        ("frame", WCOMMFrame)
    ]

    def __repr__(self) -> str:
        s = (
            f'Index: {self.index} Frame Number: {self.frame_number}\n'
            f'Timestamp: {self.timestamp} Type: {self.type}\n'
        )
        if self.type == 1:
            s += f'Frame:\n{self.frame.canFrame}\n'
        elif self.type == 2:
            s += f'Frame:\n{self.frame.sensorFrame}\n'
        return s


class NetworkManager(SensorNode, HTTPClient):
    def __init__(self,
                 *args,
                 retransmissions=1,
                 **kwargs
                 ) -> None:
        super().__init__(*args, **kwargs)
        if not isinstance(retransmissions, int):
            raise TypeError("Retransmissions must be an integer.")
        # Validate retransmissions value
        if not 0 <= retransmissions <= 3:
            raise ValueError(
                "Retransmissions must be between 0 and 3, inclusive.")
        # Node parameters
        self._id = -1
        self._index = 0
        self.members: list[Member_Node] = []  # ID of member is index in array
        self._frame_number = 0
        self.health_report: HealthReport
        self.network_stats: NetworkStats
        # Parameters for efficient communication
        self.__node_report: ct.Array[NodeReport]
        self.__report_size = 0
        self.__msg_in: COMMBlock
        self.__msg_out: COMMBlock
        self._output_buffer = []
        self._output_buffer_lock = th.Lock()
        # Paramters for retransmissions
        self.__sensor_msg_buffer = None
        self.__max_retransmissions = retransmissions
        self.__max_retrans_notified = False
        self.__attempts = 0
        self.__timeout = None
        self._timeout_additive = round((1/60), 3)
        if retransmissions > 0:
            self._timeout_additive = round(
                (self._timeout_additive / retransmissions), 3)
        logging.debug(f"Timeout additive: {self._timeout_additive}")
        self.__times_retrans = 0
        # Events and Queues for threads
        self.stop_event: th.Event
        self.in_session: th.Event
        self.output: mp.Queue
        self.__recv_timestamp = 0

    def start_session(self, ip: IPv4Address, port: int, request_data: dict) -> None:
        super().start_session(ip, port)
        self._id = request_data["ID"]
        self.members = [Member_Node] * \
            len(request_data["Devices"])  # type: ignore
        for member in request_data["Devices"]:
            self.members[member["Index"]] = Member_Node(  # type: ignore
                member["ID"], member["Devices"])
        self.__msg_in = COMMBlock()
        self.__msg_out = COMMBlock()
        with self._output_buffer_lock:
            self._output_buffer.clear()
        self.network_stats = NetworkStats(len(self.members))
        self.__report_size = ct.sizeof(NodeReport) * len(self.members)
        self.__node_report = (NodeReport * len(self.members))()
        self.output.put((OT.START_SESSION, ""))
        self._initial_health_report_wait = True  # wait for clocks to sync

    def stop_session(self) -> None:
        try:
            self._id = -1
            self.members.clear()
            self.output.put((OT.STOP_SESSION, ""))
            super().stop_session()
        except (BrokenPipeError, Full):
            pass
        finally:
            if not self.stop_event.is_set():
                self.stop_event.set()
            if self.in_session.is_set():
                self.in_session.clear()

    def request_health(self) -> None:
        # Wait until session is established, timeout after 1 second to
        # check if stop event is set
        if self.in_session.wait(1):
            if self._initial_health_report_wait:
                sleep(3.5)  # Wait for clocks to sync
                self._initial_health_report_wait = False
            self.health_report.update(
                self._index,
                self.network_stats.health_report,
                self._frame_number)
            with self.health_report.lock:
                self.health_report.counts.sim_retrans = self.__times_retrans
            self.network_stats.reset()
            self.write_health_request()

    def write_sync(self) -> None:
        self.__msg_out.index = self._index
        self.__msg_out.type = 5
        self.__msg_out.frame_number = self._frame_number
        self.sending_sync = True
        self.sync_timestamp = self.time_us()
        self.__msg_out.timestamp = self.sync_timestamp
        buffer = bytearray()
        self.pack_commblock(self.__msg_out, buffer)
        self.write(buffer, 5)

    def write_follow_up(self) -> None:
        self.__msg_out.index = self._index
        self.__msg_out.type = 6
        self.__msg_out.frame_number = self._frame_number
        self.__msg_out.timestamp = self._sync_sent_timestamp
        self.__msg_out.frame.timeFrame = self.sync_timestamp
        buffer = bytearray()
        self.pack_commblock(self.__msg_out, buffer)
        self.write(buffer, 6)

    def write_delay_resp(self, index: int, delay_req_time: int) -> None:
        self.__msg_out.index = index
        self.__msg_out.type = 8
        self.__msg_out.frame_number = self._frame_number
        self.__msg_out.timestamp = self.__recv_timestamp
        self.__msg_out.frame.timeFrame = delay_req_time
        buffer = bytearray()
        self.pack_commblock(self.__msg_out, buffer)
        self.write(buffer, 8)

    def write_health_request(self) -> None:
        self.__msg_out.index = self._index
        self.__msg_out.type = 3
        self.__msg_out.frame_number = self._frame_number
        self.__msg_out.timestamp = self.time_us()
        buffer = bytearray()
        self.pack_commblock(self.__msg_out, buffer)
        self.write(buffer, 3)

    def read_signals(self, key: sel.SelectorKey) -> None:
        try:
            signals = key.fileobj.recv()  # type: ignore
        except EOFError:
            logging.debug("Simulator IPC socket closed.")
            self.stop_session()
        else:
            if signals:
                if self.session_status == self.SessionStatus.Active:
                    self.write_signals(signals)
            else:
                logging.debug("Simulator IPC socket closed.")
                self.stop_session()

    def write_signals(self, signals) -> None:
        l = len(signals)
        if l > 16:
            l = 16
            logging.warning("Too many signals to send, truncating to 16.")
        self.__attempts = 0
        self.__max_retrans_notified = False
        for i in range(l):
            self._signals_tx[i] = signals[i]
        self.__msg_out.index = self._index
        self.__msg_out.type = 2
        self.__msg_out.frame_number = self._frame_number
        self._frame_number += 1
        self.__msg_out.timestamp = self.time_us()
        self.__msg_out.frame.sensorFrame.num_signals = l
        self.__msg_out.frame.sensorFrame.signals = self._signals_tx
        self.__sensor_msg_buffer = bytearray()
        self.pack_commblock(self.__msg_out, self.__sensor_msg_buffer)
        self._output_buffer.append((OT.SIM_MSG, (self.time_us(), *signals)))
        self.write(self.__sensor_msg_buffer, 2)

    def write_can(self, need_response: bool, fd: bool, msg: CAN_message) -> None:
        with self._sel_lock:
            self.__msg_out.index = self._index
            self.__msg_out.type = 1
            self.__msg_out.frame_number = self._frame_number
            self.__msg_out.timestamp = self.time_us()
            self.__msg_out.frame.canFrame.sequence_number = self._sequence_number
            self._sequence_number += 1
            self.__msg_out.frame.canFrame.needs_response = need_response
            self.__msg_out.frame.canFrame.fd = fd
            if fd:
                self.__msg_out.frame.canFrame.frame.can_fd.can_id = msg.can_id
                self.__msg_out.frame.canFrame.frame.can_fd.len = msg.len
                self.__msg_out.frame.canFrame.frame.can_fd.flags = msg.flags
                self.__msg_out.frame.canFrame.frame.can_fd.buf = msg.buf
            else:
                self.__msg_out.frame.canFrame.frame.can.can_id = msg.can_id
                self.__msg_out.frame.canFrame.frame.can.len = msg.len
                self.__msg_out.frame.canFrame.frame.can.buf = msg.buf
            buffer = bytearray()
            self.pack_commblock(self.__msg_out, buffer)
            with self._output_buffer_lock:
                self._output_buffer.append((OT.CAN_MSG, (
                    self.__msg_out.timestamp,
                    f"{self.__msg_out.frame.canFrame.frame.can.can_id:08X}",
                    self.__msg_out.frame.canFrame.frame.can.len,
                    bytes(self.__msg_out.frame.canFrame.frame.can.buf).hex().upper())))
            self.write(buffer, 1)
            self.output.put((OT.NOTIFY, "CAN frame sent."))

    def write(self, msg: bytes, type: int) -> None:
        if type == 5:
            super().write(msg)
            self.write_follow_up()
        if type != 2:
            super().write(msg)
        else:
            if self.__max_retransmissions == 0:
                super().write(msg)
            elif self.__attempts <= self.__max_retransmissions:
                self.__attempts += 1
                self.__timeout = self.time_us() + self._timeout_additive
                super().write(msg)

    def pack_commblock(self, msg: COMMBlock, buffer: bytearray) -> None:
        # Oddly enough this is 2x faster than using a static ctypes array and memmoves
        buffer.extend(msg.index.to_bytes(1, "little"))
        buffer.extend(msg.type.to_bytes(1, "little"))
        buffer.extend(msg.frame_number.to_bytes(4, "little"))
        buffer.extend(msg.timestamp.to_bytes(8, "little"))
        if msg.type == 1:
            self.pack_canblock(msg.frame.canFrame, buffer)
        elif msg.type == 2:
            self.pack_sensorblock(msg.frame.sensorFrame, buffer)
        elif msg.type == 6 or msg.type == 8:
            buffer.extend(msg.frame.timeFrame.to_bytes(8, "little"))

    def read(self, key: sel.SelectorKey) -> None:
        buffer = super().read()
        self.__recv_timestamp = self.time_us()
        msg_len = len(buffer)
        if msg_len >= COM_PACKED_HEAD_SIZE:
            self.unpack_commblock(self.__msg_in, buffer, msg_len)
            self.__process_commblock(self.__msg_in, msg_len)

    def unpack_commblock(self, msg: COMMBlock, buffer: bytes, msg_len: int) -> None:
        offset = 0
        msg.index = int.from_bytes(buffer[offset:offset + 1], "little")
        offset += 1
        msg.type = int.from_bytes(buffer[offset:offset + 1], "little")
        offset += 1
        msg.frame_number = int.from_bytes(buffer[offset:offset + 4], "little")
        offset += 4
        msg.timestamp = int.from_bytes(buffer[offset:offset + 8], "little")
        offset += 8
        if msg.type == 1 and (msg_len - offset) > 6:
            self.unpack_canblock(msg.frame.canFrame, buffer, offset)
        elif msg.type == 2 and (msg_len - offset) > 1:
            self.unpack_sensorblock(msg.frame.sensorFrame, buffer, offset)
        elif msg.type == 4:
            ct.memmove(self.__node_report,
                       buffer[offset:], self.__report_size)

    def __process_commblock(self, msg: COMMBlock, msg_len: int) -> None:
        if msg:
            self.members[msg.index].last_received_frame = msg.frame_number
            if msg.type == 1:
                self.members[msg.index].last_seq_num = msg.frame.canFrame.sequence_number
                self.network_stats.update(msg.index, msg_len, msg.timestamp,
                                          msg.frame.canFrame.sequence_number, self.__recv_timestamp)
                with self._output_buffer_lock:
                    self._output_buffer.append((OT.CAN_MSG, (msg.timestamp,
                                                f"{msg.frame.canFrame.frame.can.can_id:08X}",
                                                msg.frame.canFrame.frame.can.len,
                                                bytes(msg.frame.canFrame.frame.can.buf).hex().upper())))
            elif msg.type == 4:
                # count = 0
                # for i in self._node_report:
                #     logging.debug(
                #         f"Before memmove:\n"
                #         f"Node {msg.index} Member{count}: \n"
                #         f"packetLoss: {i.packetLoss}\n"
                #         f"goodput: {i.goodput}\n"
                #         f"latency: {i.latency.mean}\n"
                #         f"jitter: {i.jitter.mean}\n")
                #     count += 1
                self.health_report.update(
                    msg.index, self.__node_report, self.members[msg.index].last_seq_num)
            elif msg.type == 7:  # This is a delay request we need to respond immediately
                self.write_delay_resp(msg.index, msg.timestamp)
            if msg.frame_number == self._frame_number:
                self.__timeout = None

    def check_members(self, now: float) -> None:
        if self.__timeout and (now >= self.__timeout):
            for member in self.members[1:]:
                if self.__recvd_frame(member, now):
                    break

    def __recvd_frame(self, member: Member_Node, now: float) -> bool:
        if member.last_received_frame != self._frame_number:
            if self.__attempts <= self.__max_retransmissions:
                self.__times_retrans += 1
                self.__timeout = now + self._timeout_additive
                if self.__sensor_msg_buffer:
                    self.write(self.__sensor_msg_buffer, 2)
            elif not self.__max_retrans_notified:
                logging.error(
                    f"Have not received frame {self._frame_number} "
                    f"from device with index number {member.id} after "
                    f"{self.__max_retransmissions} attempts."
                )
                self.__max_retrans_notified = True
            return False
        else:
            return True
