from __future__ import annotations

from ctypes import POINTER, Array, Structure, c_char, c_float, c_uint8, memmove
from ipaddress import IPv4Address

from .CANNode import CANNode


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


class SensorNode(CANNode):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._signals_rx: Array[c_float]
        self._signals_tx: Array[c_float]

    def start_session(self, ip: IPv4Address, port: int) -> None:
        super().start_session(ip, port)
        self._signals_rx = (c_float * 16)()
        self._signals_tx = (c_float * 16)()
        self._signals_temp_buf = (c_char * 64)()

    def pack_sensorblock(self, block: WSenseBlock, buffer: bytearray) -> None:
        buffer.extend(block.num_signals.to_bytes(1, 'little'))
        if block.num_signals > 0:
            if block.num_signals > 16:
                block.num_signals = 16
            memmove(self._signals_temp_buf,
                    self._signals_tx, block.num_signals * 4)
            buffer.extend(self._signals_temp_buf[:block.num_signals])

    def unpack_sensorblock(self, block: WSenseBlock, buffer: bytes, offset: int) -> None:
        block.num_signals = int.from_bytes(buffer[offset:offset + 1], 'little')
        offset += 1
        if block.num_signals > 0:
            if block.num_signals > 16:
                block.num_signals = 16
            block.signals = self._signals_rx.from_buffer_copy(
                buffer[offset:offset + block.num_signals * 4])
