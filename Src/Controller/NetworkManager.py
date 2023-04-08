from __future__ import annotations

import threading as th
import logging
import selectors as sel
import ctypes as ct
import multiprocessing as mp
from time import sleep

from queue import Full
from HealthReport import HealthReport, NetworkStats, NodeReport
from HTTPClient import HTTPClient
from TUI import TUIOutput as TO
from SensorNode import SensorNode, WSenseBlock
from CANNode import CAN_message, WCANBlock, Member_Node
from Recorder import RecordType as RT
from ipaddress import IPv4Address

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
    def __init__(self, *args, retrans=2, frame_rate=60, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Node parameters
        self.id = -1
        self.index = 0
        self.members: list[Member_Node] = []  # ID of member is index in array
        self.frame_number = 0
        self.sequence_number = 0
        self.health_report: HealthReport
        self.network_stats: NetworkStats
        # Parameters for efficient communication
        self._node_report: ct.Array[NodeReport]
        self._report_size = 0
        self._msg_in: COMMBlock
        self._msg_out: COMMBlock
        self._can_output_buffer = []
        self._can_output_buffer_size = 20
        # Paramters for retransmissions
        self._max_retransmissions = retrans
        self._max_retrans_notified = False
        self._attempts = 0
        self._timeout = None
        self.timeout_additive = round((1/frame_rate), 3)
        if retrans > 0:
            self.timeout_additive = round(
                (self.timeout_additive / retrans), 3)
        logging.debug(f"Timeout additive: {self.timeout_additive}")
        self.times_retrans = 0
        # Events and Queues for threads
        self.stop_event: th.Event
        self.in_session: th.Event
        self.tui_output: mp.Queue
        self.recorder_output: mp.Queue
        self.recording = False
        self._recv_timestamp = 0

    def start_session(self, ip: IPv4Address, port: int, request_data: dict) -> None:
        super().start_session(ip, port)
        self.id = request_data["ID"]
        self.members = [Member_Node] * \
            len(request_data["Devices"])  # type: ignore
        for member in request_data["Devices"]:
            self.members[member["Index"]] = Member_Node(  # type: ignore
                member["ID"], member["Devices"])
        self._msg_in = COMMBlock()
        self._msg_out = COMMBlock()
        self._can_output_buffer = []
        self.network_stats = NetworkStats(len(self.members))
        self._report_size = ct.sizeof(NodeReport) * len(self.members)
        self._can_output_buffer_size *= len(self.members)
        self._node_report = (NodeReport * len(self.members))()
        self.tui_output.put((TO.START_SESSION, ""))
        self._initial_health_report_wait = True # wait for clocks to sync

    def stop_session(self) -> None:
        try:
            self.id = -1
            self.members.clear()
            self.tui_output.put((TO.STOP_SESSION, ""))
            super().stop_session()
        except (BrokenPipeError, Full):
            pass
        finally:
            if not self.stop_event.is_set():
                self.stop_event.set()
            if self.in_session.is_set():
                self.in_session.clear()

    def send_sync(self) -> None:
        with self.sel_lock:
            self.can_key.data.callback = self.write_sync
            self.sel.modify(self.can_key.fileobj, sel.EVENT_WRITE, self.can_key.data)
            
    def request_health(self) -> None:
        # Wait until session is established, timeout after 1 second to
        # check if stop event is set
        if self.in_session.wait(1):
            if self._initial_health_report_wait:
                sleep(3.5) # Wait for clocks to sync
                self._initial_health_report_wait = False
            self.health_report.update(
                self.index,
                self.network_stats.health_report,
                self.frame_number)
            with self.health_report.lock:
                self.health_report.counts.sim_retrans = self.times_retrans
            self.network_stats.reset()
            with self.sel_lock:
                self.can_key.data.callback = self.write_health_request
                self.can_key.data.message = None
                self.sel.modify(self.can_key.fileobj,
                                sel.EVENT_WRITE, self.can_key.data)
                
    def write_sync(self, key: sel.SelectorKey) -> None:
        with self.sel_lock:
            self._msg_out.index = self.index
            self._msg_out.type = 5
            self._msg_out.frame_number = self.frame_number
            self.sending_sync = True
            self.sync_timestamp = self.time_us()
            self._msg_out.timestamp = self.sync_timestamp
            buffer = bytearray()
            self.pack_commblock(self._msg_out, buffer)
            self.write(buffer, 5, key)

    def write_follow_up(self, key: sel.SelectorKey) -> None:
        self._msg_out.index = self.index
        self._msg_out.type = 6
        self._msg_out.frame_number = self.frame_number
        self._msg_out.timestamp = self.sync_sent_timestamp
        self._msg_out.frame.timeFrame = self.sync_timestamp
        buffer = bytearray()
        self.pack_commblock(self._msg_out, buffer)
        self.write(buffer, 6, key)

    def write_delay_resp(self, key: sel.SelectorKey, index: int, delay_req_time: int) -> None:
        with self.sel_lock:
            self._msg_out.index = index
            self._msg_out.type = 8
            self._msg_out.frame_number = self.frame_number
            self._msg_out.timestamp = self._recv_timestamp
            self._msg_out.frame.timeFrame = delay_req_time
            buffer = bytearray()
            self.pack_commblock(self._msg_out, buffer)
            self.write(buffer, 8, key)

    def write_health_request(self, key: sel.SelectorKey) -> None:
        with self.sel_lock:
            self._msg_out.index = self.index
            self._msg_out.type = 3
            self._msg_out.frame_number = self.frame_number
            self._msg_out.timestamp = self.time_us()
            buffer = bytearray()
            self.pack_commblock(self._msg_out, buffer)
            self.write(buffer, 3, key)

    def read_signals(self, key: sel.SelectorKey) -> None:
        try:
            signals = key.fileobj.recv()  # type: ignore
        except EOFError:
            logging.debug("Simulator IPC socket closed.")
            self.stop_session()
        else:
            if signals:
                if self.session_status == self.SessionStatus.Active:
                    self.tui_output.put((TO.SIM_MSG, signals))
                    with self.sel_lock:
                        self.can_key.data.callback = self.write_signals
                        self.can_key.data.message = signals
                        self.sel.modify(self.can_key.fileobj,
                                        sel.EVENT_WRITE, self.can_key.data)
            else:
                logging.debug("Simulator IPC socket closed.")
                self.stop_session()

    def write_signals(self, key: sel.SelectorKey) -> None:
        with self.sel_lock:
            l = len(key.data.message)
            if l > 16:
                l = 16
                logging.warning("Too many signals to send, truncating to 16.")
            self._attempts = 0
            self._max_retrans_notified = False
            for i in range(l):
                self.signals_tx[i] = key.data.message[i]
            self._msg_out.index = self.index
            self._msg_out.type = 2
            self._msg_out.frame_number = self.frame_number
            self.frame_number += 1
            self._msg_out.timestamp = self.time_us()
            self._msg_out.frame.sensorFrame.num_signals = l
            self._msg_out.frame.sensorFrame.signals = self.signals_tx
            buffer = bytearray()
            self.pack_commblock(self._msg_out, buffer)
            if self.recording:
                self.recorder_output.put(
                    (RT.SIM, (self.time_us(), *key.data.message)))
            self.write(buffer, 2, key)

    def write_can(self, key: sel.SelectorKey) -> None:
        with self.sel_lock:
            self._msg_out.index = self.index
            self._msg_out.type = 1
            self._msg_out.frame_number = self.frame_number
            self._msg_out.timestamp = self.time_us()
            self._msg_out.frame.canFrame.sequence_number = self.sequence_number
            self.sequence_number += 1
            self._msg_out.frame.canFrame.needs_response = key.data.message[0]
            self._msg_out.frame.canFrame.fd = key.data.message[1]
            if key.data.message[1]:
                self._msg_out.frame.canFrame.frame.can_fd.can_id = key.data.message[2].can_id
                self._msg_out.frame.canFrame.frame.can_fd.len = key.data.message[2].len
                self._msg_out.frame.canFrame.frame.can_fd.flags = key.data.message[2].flags
                self._msg_out.frame.canFrame.frame.can_fd.buf = key.data.message[2].buf
            else:
                self._msg_out.frame.canFrame.frame.can.can_id = key.data.message[2].can_id
                self._msg_out.frame.canFrame.frame.can.len = key.data.message[2].len
                self._msg_out.frame.canFrame.frame.can.buf = key.data.message[2].buf
            buffer = bytearray()
            self.pack_commblock(self._msg_out, buffer)
            buf_str = f"{self._msg_out.frame.canFrame.frame.can.buf:X}"
            self.tui_output.put((TO.CAN_MSG, [(
                self._msg_out.frame.canFrame.frame.can.can_id,
                self._msg_out.frame.canFrame.frame.can.len,
                buf_str)]))
            if self.recording:
                self.recorder_output.put((RT.CAN, (
                    self.time_us(),
                    self._msg_out.frame.canFrame.frame.can.can_id,
                    buf_str)))
            self.write(buffer, 1, key)
            self.tui_output.put((TO.NOTIFY, "CAN frame sent."))

    def write(self, msg: bytes, type: int, key: sel.SelectorKey) -> None:
        if type == 5:
            super().write(msg)
            self.write_follow_up(key)
        if type != 2:
            super().write(msg)
        else:
            if self._max_retransmissions == 0:
                super().write(msg)
            elif self._attempts <= self._max_retransmissions:
                self._attempts += 1
                self._timeout = self.time_us() + self.timeout_additive
                super().write(msg)
        key.data.callback = self.read
        self.sel.modify(key.fileobj, sel.EVENT_READ, key.data)

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
        self._recv_timestamp = self.time_us()
        msg_len = len(buffer)
        if msg_len >= COM_PACKED_HEAD_SIZE:
            self.unpack_commblock(self._msg_in, buffer, msg_len)
            self.__process_commblock(self._msg_in, msg_len, key)

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
            ct.memmove(self._node_report, buffer[offset:], len(buffer[offset:]))

    def __process_commblock(self, msg: COMMBlock, msg_len: int, key: sel.SelectorKey) -> None:
        if msg:
            self.members[msg.index].last_received_frame = msg.frame_number
            if msg.type == 1:
                self.members[msg.index].last_seq_num = msg.frame.canFrame.sequence_number
                self.network_stats.update(msg.index, msg_len, msg.timestamp,
                                          msg.frame.canFrame.sequence_number, self._recv_timestamp)
                buf_str = bytes(msg.frame.canFrame.frame.can.buf).hex().upper()
                self._can_output_buffer.append((f"{msg.frame.canFrame.frame.can.can_id:X}",
                                                msg.frame.canFrame.frame.can.len,
                                                buf_str))
                if len(self._can_output_buffer) > self._can_output_buffer_size:
                    self.tui_output.put((TO.CAN_MSG, self._can_output_buffer.copy()))
                    self._can_output_buffer.clear()
                if self.recording:
                    self.recorder_output.put((RT.CAN, (
                        msg.timestamp,
                        msg.frame.canFrame.frame.can.can_id,
                        buf_str)))
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
                    msg.index, self._node_report, self.members[msg.index].last_seq_num)
            elif msg.type == 7: # This is a delay request we need to respond immediately
                self.write_delay_resp(key, msg.index, msg.timestamp)
            if msg.frame_number == self.frame_number:
                self._timeout = None

    def check_members(self, now: float) -> None:
        if self._timeout and (now >= self._timeout):
            for member in self.members[1:]:
                if self.__recvd_frame(member, now):
                    break

    def __recvd_frame(self, member: Member_Node, now: float) -> bool:
        if member.last_received_frame != self.frame_number:
            if self._attempts <= self._max_retransmissions:
                self.times_retrans += 1
                self._timeout = now + self.timeout_additive
                with self.sel_lock:
                    self.can_key.data.callback = self.write
                    self.sel.modify(self.can_key.fileobj,
                                    sel.EVENT_WRITE, self.can_key.data)
            elif not self._max_retrans_notified:
                logging.error(
                    f"Have not received frame {self.frame_number} "
                    f"from device with index number {member.id} after "
                    f"{self._max_retransmissions} attempts."
                )
                self._max_retrans_notified = True
            return False
        else:
            return True
