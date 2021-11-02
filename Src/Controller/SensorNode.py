from CANNode import CANNode
from ctypes import *


class WSenseBlock(Structure):
    _fields_ = [
        ("num_signals", c_uint8),
        ("signals", c_float * 19)
    ]

    def __repr__(self) -> str:
        s = f'num_signals: {self.num_signals} signals:\n'
        for i in range(self.num_signals):
            s += f'{self.signals[i]}\n'
        return s

class SensorNode(CANNode):
    def __init__(self) -> None:
        super(SensorNode, self).__init__()

    def packSignals(self, *sensors: float) -> WSenseBlock:
        return WSenseBlock(len(sensors), sensors)

    