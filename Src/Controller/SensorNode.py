import logging
from CANNode import CANNode, WCANBlock
from ctypes import *
from typing import List, Tuple
from selectors import *
from ipaddress import IPv4Address
from time import time


class WSenseBlock(Structure):
    _fields_ = [
        ("num_signals", c_uint8),
        ("signals", POINTER(c_float))
    ]

    def __repr__(self) -> str:
        s = f'num_signals: {self.num_signals} signals:\n'
        for i in range(self.num_signals):
            s += f'{self.signals[i]}\n'
        return s

class WCOMMFrame(Union):
    _fields_ = [
        ("canFrame", WCANBlock),
        ("sensorFrame", WSenseBlock)
    ]

class COMMBlock(Structure):
    _fields_ = [
        ("index", c_uint32),
        ("frame_number", c_uint32),
        ("timestamp", c_uint32),
        ("type", c_uint8),
        ("frame", WCOMMFrame)
    ]

    def __repr__(self) -> str:
        s =  (
            f'Index: {self.index} Frame Number: {self.frame_number}\n'
            f'Timestamp: {self.timestamp} Type: {self.type}\n'
        )
        if self.type == 1:
            s += f'Frame:\n{self.frame.canFrame}\n'
        elif self.type == 2:
            s += f'Frame:\n{self.frame.sensorFrame}\n'
        return s

class Member_Node():
    def __init__(self, _id = -1, _devices = None) -> None:
        self.id = _id
        self.devices = _devices
        self.last_received_frame = -1
        self.health_report = None

class SensorNode(CANNode):
    def __init__(self, *, _max_retrans = 3, _max_frame_rate = 60, **kwargs) -> None:
        super().__init__()
        self.id = -1
        self.index = 0
        self.members: List[Member_Node] = [] # ID of member is index in array

        self.max_retransmissions = _max_retrans
        self.max_retrans_notified = False
        self.attempts = 0
        self.timeout = None
        self.timeout_additive = (1/_max_frame_rate) * (_max_retrans)   
        self.frame_number = 1

    def start_session(self, ip: IPv4Address, port: int, request_data: dict) -> None:
        super().start_session(ip, port)
        self.id = request_data["ID"]
        self.members = [Member_Node] * len(request_data["Devices"])
        for member in request_data["Devices"]:
            self.members[member["Index"]] = Member_Node(
                member["ID"], member["Devices"]
                )

    def stop_session(self) -> None:
        self.id = -1
        self.members.clear()
        super().stop_session()

    def packSensorData(self, *sensors: float) -> bytes:
        self.attempts = 0
        self.max_retrans_notified = False
        signalArray = c_float * len(sensors)
        signals = signalArray(*sensors)
        msg = COMMBlock(
            self.index,
            self.frame_number,
            int(time() * 1000),
            2,
            WCOMMFrame(WCANBlock(), WSenseBlock(
                len(sensors), signals
                ))
        )
        msg = bytes(msg)[:-4] + bytes(signals)
        self.frame_number += 1
        return msg

    def write(self, *msg: COMMBlock) -> int:
        if self.attempts <= self.max_retransmissions:
            self.attempts += 1
            self.timeout = time() + self.timeout_additive
            return super().write(*msg)
        elif not self.max_retrans_notified:
            logging.error(
                f"Have not received frame #{self.frame_number} "
                f"from device with index number {id} after "
                f"{self.max_retransmissions} attempts."
                )
            self.max_retrans_notified = True

    def read(self) -> Tuple[COMMBlock, bytes]:
        try:
            buffer = super().read()
            buffer = buffer + b'0000'
            if buffer:
                msg = COMMBlock.from_buffer_copy(buffer[:sizeof(COMMBlock)])
                self.members[msg.index].last_received_frame = msg.frame_number
                return msg, buffer
            else:
                return None
        except (AttributeError, ValueError) as ae:
            logging.error("Received data from an out of band device.")
            logging.error(ae)
            return None

    def __recvd_frame(self, member: Member_Node, current_time: float) -> bool:
        not_recvd = member.last_received_frame != self.frame_number
        timedout = current_time >= self.timeout
        if not_recvd and timedout:
            with self.sel_lock:
                self.sel.modify(
                    self.can_key.fileobj,
                    EVENT_WRITE,
                    self.can_key.data
                    )
            return False

    def check_members(self) -> None:
        if not self.timeout:
            return
        current_time = time()
        for member in self.members:
            if self.__recvd_frame(member, current_time):
                break
