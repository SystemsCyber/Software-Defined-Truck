import logging
import selectors as sel
import struct
from ctypes import (POINTER, Structure, Union, c_float, c_uint8, c_uint32,
                    c_uint64, sizeof)
from ipaddress import IPv4Address
from time import time
from typing import List, Tuple

from CANNode import CANNode, WCANBlock


class WSenseBlock(Structure):
    _pack_ = 4
    _fields_ = [
        ("num_signals", c_uint8),
        # Remember this machine is 64-bit and teensy is 32-bit
        ("signals", POINTER(c_float))
    ]

    def __repr__(self) -> str:
        s = f'num_signals: {self.num_signals} signals:\n'
        for i in range(self.num_signals):
            s += f'{self.signals[i]} '
        return s


class WCOMMFrame(Union):
    _fields_ = [
        ("canFrame", WCANBlock),
        ("sensorFrame", WSenseBlock)
    ]


class COMMBlock(Structure):
    _anonymous_ = ("frame",)
    _pack_ = 4
    _fields_ = [
        ("index", c_uint32),
        ("frame_number", c_uint32),
        ("timestamp", c_uint64),
        ("type", c_uint8),
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


class Member_Node():
    def __init__(self, _id=-1, _devices=None) -> None:
        self.id = _id
        self.devices = _devices
        self.last_received_frame = 1
        self.last_seq_num = 1
        self.health_report = None


class SensorNode(CANNode):
    def __init__(self, *args, _retrans=2, _frame_rate=60, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._id = -1
        self.index = 0
        self.members: List[Member_Node] = []  # ID of member is index in array

        self._max_retransmissions = _retrans
        self._max_retrans_notified = False
        self._attempts = 0
        self._timeout = None
        self.timeout_additive = (1/_frame_rate)
        if _retrans > 0:
            self.timeout_additive /= (_retrans)
        logging.debug(f"Timeout additive: {self.timeout_additive}")

        self.frame_number = 0
        self.comm_head_size = sizeof(COMMBlock) - sizeof(WCOMMFrame)
        self._signal_offset = self.comm_head_size + 4
        self.times_retrans = 0

    def start_session(self, ip: IPv4Address, port: int, request_data: dict) -> None:
        super().start_session(ip, port)
        self._id = request_data["ID"]
        self.members = [Member_Node] * len(request_data["Devices"])
        for member in request_data["Devices"]:
            self.members[member["Index"]] = Member_Node(
                member["ID"], member["Devices"]
            )

    def stop_session(self) -> None:
        self._id = -1
        self.members.clear()
        super().stop_session()

    def packSensorData(self, *sensors: float) -> bytes:
        l = len(sensors)
        self._attempts = 0
        self._max_retrans_notified = False
        signalArray = c_float * l
        signals = signalArray(*sensors)
        self.frame_number += 1
        msg = COMMBlock(self.index, self.frame_number, self.time_client.time_ms(), 2,
                        WCOMMFrame(WCANBlock(), WSenseBlock(l, signals)))
        return bytes(msg)[:self._signal_offset] + struct.pack(f"<{l}f", *signals)

    def write(self, *msg: bytes) -> int:
        if self._max_retransmissions == 0:
            return super().write(*msg)
        elif self._attempts <= self._max_retransmissions:
            self._attempts += 1
            self._timeout = time() + self.timeout_additive
            return super().write(*msg)

    def read(self) -> Tuple[COMMBlock, bytes]:
        try:
            buffer = super().read()
            if buffer and len(buffer) >= sizeof(COMMBlock):
                msg = COMMBlock.from_buffer_copy(buffer)
                self.members[msg.index].last_received_frame = msg.frame_number
                if msg.type == 1:
                    self.members[msg.index].last_seq_num = msg.frame.canFrame.sequence_number
                if msg.frame_number == self.frame_number:
                    self._timeout = None
                return msg, buffer
            else:
                return (None, None)
        except (AttributeError, ValueError) as ae:
            logging.error("Received data from an out of band device.")
            logging.error(ae)
            return (None, None)

    def __recvd_frame(self, member: Member_Node, now: float) -> bool:
        if member.last_received_frame != self.frame_number:
            if self._attempts <= self._max_retransmissions:
                self.times_retrans += 1
                self._timeout = now + self.timeout_additive
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

    def check_members(self, now: float) -> None:
        if self._timeout and (now >= self._timeout):
            for member in self.members[1:]:
                if self.__recvd_frame(member, now):
                    break
