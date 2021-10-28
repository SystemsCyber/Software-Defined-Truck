import struct
from collections import namedtuple
from typing import Tuple
from CANNode import CANNode
from Frame import CAN_Message_T

class SensorNode(CANNode):
    def __init__(self, _max_retransmissions: int) -> None:
        self.frame_num = 0
        self.last_frame_num = 0
        self.frame_rate = 0
        self.retransmission_timeout = 0
        self.max_retransmissions = _max_retransmissions
        super(SensorNode, self).__init__()

    def write(self, message) -> None:
        if isinstance(message, CAN_Message_T):
            return super().write(message)
        else:
            if self.frame_num == 4294967296:
                self.frame_num = 0
            else:
                self.frame_num += 1
            self.last_frame_num = self.frame_num
            self.last_frame = message
            packed_message = struct.pack("Ifff???B",
                           self.frame_num,              # Frame number
                           message.throttle,            # Throttle
                           message.steer,               # Steering
                           message.brake,               # Braking
                           message.hand_brake,          # Hand Brake
                           message.reverse,             # Reverse
                           message.manual_gear_shift,   # Manual
                           message.gear)                # Gear
            return super().write(packed_message)

    