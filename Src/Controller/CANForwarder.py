import struct
from collections import namedtuple
from typing import Tuple

can_frame = namedtuple("can_frame", [
            "device_id",
            "control_frame_ref",
            "sequence_number",
            "can_id",
            "timestamp",
            "id_hit",
            "extended",
            "remote",
            "overrun",
            "reserved",
            "data_length",
            "data",
            "mailbox",
            "bus",
            "sequential_frame"
            ])

class CANForwarder:
    def __init__(self) -> None:
        self.frame_num = 0
        self.last_frame = 0

    def packControlFrame(self, control) -> bytes:
        self.last_frame = self.frame_num
        return struct.pack("Ifff???B",
                           self.frame_num,              # Frame number
                           control.throttle,            # Throttle
                           control.steer,               # Steering
                           control.brake,               # Braking
                           control.hand_brake,          # Hand Brake
                           control.reverse,             # Reverse
                           control.manual_gear_shift,   # Manual
                           control.gear)                # Gear

    def unpackCanFrame(self, buffer, verbose=False) -> Tuple:
        rawCanFrame = struct.unpack("IIIIHB????Bs8bB?x", buffer)
        cf = can_frame(
            device_id = rawCanFrame[0],
            control_frame_ref = rawCanFrame[1],
            sequence_number = rawCanFrame[2],
            can_id = rawCanFrame[3],
            timestamp = rawCanFrame[4],
            id_hit = rawCanFrame[5],
            extended = rawCanFrame[6],
            remote = rawCanFrame[7],
            overrun = rawCanFrame[8],
            reserved = rawCanFrame[9],
            data_length = rawCanFrame[10],
            data = rawCanFrame[11],
            mailbox = rawCanFrame[12],
            bus = rawCanFrame[13],
            sequential_frame = rawCanFrame[14]
        )
        if verbose:
            printout = (
                f'Device: {cf.device_id:>5d}\n'
                f'Frame #: {cf.control_frame_ref:>8d} Seq. #: {cf.sequence_number:>10d}\n'
                f'\tID: {cf.can_id} Timestamp: {cf.timestamp} IDHit: {cf.id_hit}\n'
                f'\tExtended: {cf.extended} Remote: {cf.remote} Overrun: {cf.overrun} Reserved: {cf.reserved}\n'
                f'\tLength: {cf.data_length} Data: {cf.data}\n'
                f'\tMailbox: {cf.mailbox} Bus: {cf.bus} SeqFrame: {cf.sequential_frame}\n'
            )
            print(printout)
        return cf
