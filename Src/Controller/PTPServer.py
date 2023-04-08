from __future__ import annotations

from enum import Enum, auto
import time
import ctypes as ct

# THIS IS A MODIFIED VERSION OF THE PRECISION TIME PROTOCOL

class PTPMessageType(Enum):
    Sync = auto()
    Delay_Req = auto()
    Follow_Up = auto()
    Delay_Resp = auto()
    Other = auto()

class TimeBlock(ct.Structure):
    _pack_ = 4
    _fields_ = [
        ("msgType", ct.c_uint8),
        ("index", ct.c_uint8),
        ("timestamp", ct.c_uint64) # 64-bit timestamp in microseconds, not nanoseconds because the teensy can't handle that
    ]

class PTPServer(object):
    @staticmethod
    def create_sync_packet(block: TimeBlock) -> None:
        block.msgType = PTPMessageType.Sync.value
        block.index = 0
        block.timestamp = time.time_ns() // 1000
    
    @staticmethod
    def create_delay_packet(block: TimeBlock, index: int) -> None:
        block.msgType = PTPMessageType.Delay_Resp.value
        block.index = index
        block.timestamp = time.time_ns() // 1000
    
    @staticmethod
    def pack_timeblock(frame: TimeBlock, buffer: bytearray) -> None:
        buffer.extend(frame.msgType.to_bytes(1, "little"))
        buffer.extend(frame.index.to_bytes(1, "little"))
        buffer.extend(frame.timestamp.to_bytes(8, "little"))

    @staticmethod
    def unpack_timeblock(frame: TimeBlock, buffer: bytearray) -> None:
        frame.msgType = int.from_bytes(buffer[0:1], "little")
        frame.index = int.from_bytes(buffer[1:2], "little")
        frame.timestamp = int.from_bytes(buffer[2:10], "little")