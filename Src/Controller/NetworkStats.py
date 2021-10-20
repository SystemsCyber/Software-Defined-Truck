from time import time
from typing import NamedTuple


class NetworkStats:

    def __init__(self, _id: int) -> None:
        self.id = _id
        self.latency = 0.0
        self.msg_count = 0
        self.last_frame_number = 0
        self.last_seq_number = 0
        self.dropped_can_frames = 0
        self.dropped_carla_frames = 0
        self.last_can_message_time = time()

    def calculate_stats(self, can_frame: NamedTuple, last_frame: int, sent_time: float) -> None:
        self.msg_count += 1
        self.last_frame_number = max(self.last_frame_number, can_frame.control_frame_ref)
        self.latency = self.__calc_latency(sent_time, self.msg_count, self.latency)
        self.dropped_can_frames = self.__check_can_frame(can_frame, self.last_seq_number)
        self.dropped_carla_frames = self.__check_carla_frame(can_frame, last_frame)
        if can_frame.sequence_number == 4294967296:
            self.last_seq_number = -1
        else:
            self.last_seq_number = can_frame.sequence_number

    def __calc_latency(self, sent_time: float, msg_count: int, avg_rtt: float) -> float:
        # From: https://stackoverflow.com/questions/22999487/update-the-average-of-a-continuous-sequence-of-numbers-in-constant-time
        new_rtt = self.last_can_message_time - sent_time
        return avg_rtt + ((new_rtt - avg_rtt) / msg_count)

    def __check_can_frame(self, can_frame: NamedTuple, last_seq_number: int) -> int:
        sequence_difference = can_frame.sequence_number - last_seq_number
        if sequence_difference > 1:
            return sequence_difference
        else:
            return 0

    def __check_carla_frame(self, can_frame: NamedTuple, last_frame: int) -> int:
        frame_difference = last_frame - can_frame.control_frame_ref
        if frame_difference > 1:
            return frame_difference
        else:
            return 0

    def __repr__(self):
        return (
            f'[{self.id}]:\n'
            f'\tLatency: {self.latency:>5.2f}ms\n'
            f'\tDropped Carla Frames: {self.dropped_carla_frames}\n'
            f'\tDropped CAN Frames: {self.dropped_can_frames}\n'
        )