from __future__ import annotations
import queue
from time import sleep
import numpy as np
import logging
import copy
import multiprocessing as mp
from multiprocessing.synchronize import Event
from multiprocessing.sharedctypes import RawArray, RawValue
import ctypes as ct
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

from CANNode import Member_Node
from Time_Client import Time_Client
from NetworkMatrix import NetworkMatrix


@dataclass
class HealthBasics:
    last_message_time: float = 0.0
    last_sequence_number: int = 0


class HealthCore(ct.Structure):
    _pack_ = 4
    _fields_ = [
        ("count", ct.c_uint32),
        ("min", ct.c_float),
        ("max", ct.c_float),
        ("mean", ct.c_float),
        ("variance", ct.c_float),
        ("sumOfSquaredDifferences", ct.c_float)
    ]

    def __repr__(self) -> str:
        return (
            f'\tCount: {self.count} Min: {self.min} Max: {self.max}\n'
            f'\tMean: {self.mean} Variance: {self.variance}\n'
            f'\tSumOfSquaredDifferences: {self.sumOfSquaredDifferences}\n'
        )


class NodeReport(ct.Structure):
    _pack_ = 4
    _fields_ = [
        ("packetLoss", ct.c_uint32),
        ("goodput", ct.c_uint32),
        ("latency", HealthCore),
        ("jitter", HealthCore)
    ]

    def __repr__(self) -> str:
        return (
            f'PacketLoss: {self.packetLoss}\n'
            f'Latency: \n{self.latency}\n'
            f'Jitter: \n{self.jitter}\n'
            f'Goodput: \n{self.goodput}\n'
        )


class NetworkStats:
    def __init__(self, _num_members: int) -> None:
        try:
            self.size = _num_members
            self.basics = [HealthBasics() for _ in range(_num_members)]
            self.health_report = (NodeReport * _num_members)()
            for i in range(_num_members):
                self.health_report[i].packetLoss = 0
                self.health_report[i].goodput = 0
                ct.memset(ct.pointer(
                    self.health_report[i].latency), 0, ct.sizeof(HealthCore))
                ct.memset(ct.pointer(
                    self.health_report[i].jitter), 0, ct.sizeof(HealthCore))
        except Exception as e:
            logging.error(f'NetworkStats: {e}', exc_info=True)

    def update(self, i: int, packet_size: int, timestamp: int, sequence_number: int, now: int):
        delay = (now - timestamp) // 1000
        # if these numbers are zero then this is the first messages we've received
        if (self.basics[i].last_message_time != 0) and (self.basics[i].last_sequence_number != 0):
            # logging.debug(f'Controller Recv: {now} SSSF Send: {timestamp} Diff: {delay}')
            self.calculate(self.health_report[i].latency, abs(delay))
            self.calculate(
                self.health_report[i].jitter, self.health_report[i].latency.variance)
            # If no packet loss then sequence number = last sequence number + 1
            packetsLost = sequence_number - \
                (self.basics[i].last_sequence_number + 1)
            # If packetsLost is negative then this usually indicates duplicate or
            # out of order frame.
            self.health_report[i].packetLoss += packetsLost if packetsLost > 0 else 0
            self.health_report[i].goodput += packet_size

        self.basics[i].last_message_time = now
        self.basics[i].last_sequence_number = sequence_number

    def reset(self):
        for i in range(self.size):
            self.health_report[i].packetLoss = 0
            self.health_report[i].goodput = 0
            ct.memset(ct.pointer(
                self.health_report[i].latency), 0, ct.sizeof(HealthCore))
            ct.memset(ct.pointer(
                self.health_report[i].jitter), 0, ct.sizeof(HealthCore))

    def calculate(self, edge: HealthCore, n: float):
        # From: https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance#Welford's_online_algorithm
        edge.min = min(edge.min, n)
        edge.max = max(edge.max, n)
        edge.count += 1
        delta = n - edge.mean
        edge.mean += delta / edge.count
        delta2 = n - edge.mean
        edge.sumOfSquaredDifferences += delta * delta2
        edge.variance = edge.sumOfSquaredDifferences / edge.count


class HealthCounts(ct.Structure):
    _pack_ = 4
    _fields_ = [
        ("sim_frames", ct.c_uint32),
        ("can_frames", ct.c_uint32),
        ("dropped_sim_frames", ct.c_uint32),
        ("dropped_can_frames", ct.c_uint32),
        ("sim_retrans", ct.c_uint32)
    ]

    def __repr__(self) -> str:
        return (
            f'\tSimulator Frame Count: {self.sim_frames}\n'
            f'\tCAN Frame Count: {self.can_frames}\n'
            f'\tDropped Simulator Frames: {self.dropped_sim_frames}\n'
            f'\tDropped CAN Frames: {self.dropped_can_frames}\n'
        )

class HealthReport:
    def __init__(self, members: List[Member_Node], report_offset=14) -> None:
        _num_members = len(members)
        self.lock = mp.Lock()
        self._members = members
        self._rx_report_offset = report_offset
        self._rx_report_size = ct.sizeof(NodeReport) * _num_members
        self.report = [RawArray(NodeReport, _num_members)
                       for _ in range(_num_members)]
        for i in range(_num_members):
            ct.memset(ct.addressof(
                self.report[i]), 0, ct.sizeof(self.report[i]))
        self.counts = RawValue(HealthCounts, 0)
        self.can_frames_per_device = RawArray(ct.c_uint32, [0] * _num_members)
        self.labels = self.__create_axis_names()
        self._matrix = NetworkMatrix(_num_members, self.labels)

    # From:
    # https://stackoverflow.com/questions/2837409/how-to-append-count-numbers-to-duplicates-in-a-list-in-python
    def __rename_duplicates(self, old):
        seen = {}
        for x in old:
            if x in seen:
                seen[x] += 1
                yield f"{x}{seen[x]}"
            else:
                seen[x] = 0
                yield x

    def __create_axis_names(self) -> list:
        axis_names = []
        for i in self._members:
            combined_device_name = ""
            if isinstance(i.devices[0], dict):
                for j in i.devices:
                    if j == i.devices[-1]:
                        combined_device_name += j["Type"][0]
                    else:
                        combined_device_name += f"{j['Type'][0]}_"
            else:
                combined_device_name += i.devices[0]
            axis_names.append(combined_device_name)
        axis_names = list(self.__rename_duplicates(axis_names))
        return axis_names

    def update(self, index: int, report_buff: ct.Array[NodeReport], last_msg_num: int):
        with self.lock:
            if index == 0:
                self.counts.sim_frames = last_msg_num
            else:
                self.counts.can_frames -= self.can_frames_per_device[index]
                self.counts.can_frames += last_msg_num
                self.can_frames_per_device[index] = last_msg_num
            ct.memmove(self.report[index], report_buff, self._rx_report_size)
            # for i in range(len(self._members)):
            #     for j in range(len(self._members)):
            #         logging.debug(
            #             f"After memmove:\n"
            #             f"Node {i} Member{j}: \n"
            #             f"packetLoss: {self.report[i][j].packetLoss}\n"
            #             f"latency: {self.report[i][j].latency.mean}\n"
            #             f"jitter: {self.report[i][j].jitter.mean}\n"
            #             f"goodput: {self.report[i][j].goodput.mean}")

    def start_display(
        self,
        stop_event: Event,
        output: mp.Queue,
        log_queue: mp.Queue,
        log_level: int
    ) -> None:
        try:
            self.matrix_proc = mp.Process(
                target=self._matrix.animate,
                args=(self.lock, stop_event, self.report, self.counts,
                      output, log_queue, log_level),
                daemon=True)
            self.matrix_proc.start()
        except Exception as e:
            logging.error(e, exc_info=True)

    def stop_display(self) -> None:
        try:
            if hasattr(self, "matrix_proc") and self.matrix_proc is not None:
                self.matrix_proc.terminate()
                self.matrix_proc.join(1)
                self.matrix_proc.close()
        except Exception as e:
            logging.error(e, exc_info=True)


# if __name__ == "__main__":
#         ns = NetworkStats(6, Time_Client([""]))


# if __name__ == "__main__":
#     import time
#     stop = mp.Event()
#     log_queue = mp.Queue()
#     log_level = logging.DEBUG
#     hr = HealthReport([
#         Member_Node(0, [{"Type": ["ECU", "Electronic Control Unit"]}]),
#         Member_Node(1, [{"Type": ["ECU", "Electronic Control Unit"]}]),
#         Member_Node(2, [{"Type": ["ECU", "Electronic Control Unit"]}]),
#         Member_Node(3, [{"Type": ["ECU", "Electronic Control Unit"]}])])
#     hr.start_display(stop, log_queue, log_level)
#     time.sleep(10)
#     hr.stop_display()
#     while True:
#         if not log_queue.empty():
#             print(log_queue.get())
#         else:
#             break


def generate_random_members(num_members: int) -> list[Member_Node]:
    members = []
    for i in range(num_members):
        members.append(Member_Node(
            i, [{"Type": "CAN", "ID": "0x123", "Name": "Test"}]))
    return members


if __name__ == "__main__":
    print(ct.sizeof(HealthCore))
    print(ct.sizeof(NodeReport))
    can_timestamps = []
    global last_timestamp
    last_timestamp = 0
    stop_event = mp.Event()
    output = mp.Queue()
    log_queue = mp.Queue()
    health_report = HealthReport(generate_random_members(3))
    health_report.start_display(stop_event, output, log_queue, logging.DEBUG)
    report = (NodeReport * 3)()
    buf = (ct.c_byte * (ct.sizeof(NodeReport) * 3))()
    index = 0
    msg_num = 0
    while True:
        try:
            for i in range(3):
                report[i].packetLoss = np.random.randint(0, 2)
                report[i].latency.mean = np.random.randint(0, 10)
                report[i].jitter.mean = np.random.randint(0, 10)
                report[i].goodput = np.random.randint(50000, 60000)
            ct.memmove(buf, ct.addressof(report), ct.sizeof(report))
            # health_report.update(index, buf, msg_num)
            index = (index + 1) % 3
            msg_num += np.random.randint(0, 100)
            # for i in range(3):
            #     print(f"packetLoss: {report[i].packetLoss}")
            #     print(f"latency: {report[i].latency.mean}")
            #     print(f"jitter: {report[i].jitter.mean}")
            #     print(f"goodput: {report[i].goodput.mean}")
            sleep(0.33)
            try:
                print(output.get_nowait())
                print(log_queue.get_nowait())
            except queue.Empty:
                pass

        except KeyboardInterrupt:
            break
    stop_event.set()
    health_report.stop_display()
