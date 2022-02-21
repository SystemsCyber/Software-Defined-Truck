import copy
from ctypes import Structure, c_float, c_uint32
from dataclasses import dataclass
from time import time
from typing import Dict, Tuple

from pandas import DataFrame

from Time_Client import Time_Client

@dataclass
class HealthBasics:
    last_message_time: float = 0.0
    last_sequence_number: int = 0


class HealthCore(Structure):
    _pack_ = 4
    _fields_ = [
        ("count", c_uint32),
        ("min", c_float),
        ("max", c_float),
        ("mean", c_float),
        ("variance", c_float),
        ("sumOfSquaredDifferences", c_float)
    ]

    def __repr__(self) -> str:
        return (
            f'\tCount: {self.count} Min: {self.min} Max: {self.max}\n'
            f'\tMean: {self.mean} Variance: {self.variance}\n'
            f'\tSumOfSquaredDifferences: {self.sumOfSquaredDifferences}\n'
        )


class NodeReport(Structure):
    _pack_ = 4
    _fields_ = [
        ("packetLoss", c_float),
        ("latency", HealthCore),
        ("jitter", HealthCore),
        ("goodput", HealthCore)
    ]

    def __repr__(self) -> str:
        return (
            f'PacketLoss: {self.packetLoss}\n'
            f'Latency: \n{self.latency}\n'
            f'Jitter: \n{self.jitter}\n'
            f'Goodput: \n{self.goodput}\n'
        )


class NetworkStats:
    def __init__(self, _num_members: int, _time_client: Time_Client) -> None:
        self.size = _num_members
        self.time_client = _time_client
        self.basics = [HealthBasics()] * _num_members
        self.health_report = [NodeReport(
            0.0,
            HealthCore(0, float('inf'), -float('inf'), 0.0, 0.0, 0.0),
            HealthCore(0, float('inf'), -float('inf'), 0.0, 0.0, 0.0),
            HealthCore(0, float('inf'), -float('inf'), 0.0, 0.0, 0.0)
        )] * _num_members

    def update(self, i: int, packet_size: int, timestamp: int, sequence_number: int):
        now = self.time_client.time_ms()
        delay = now - timestamp
        # print(f'Controller Recv: {now} SSSF Send: {timestamp} Diff: {delay}')
        ellapsedSeconds = (now - self.basics[i].last_message_time) / 1000.0
        if ellapsedSeconds == 0.0:
            ellapsedSeconds = 0.0001  # Retransmission

        self.calculate(self.health_report[i].latency, abs(delay))
        self.calculate(
            self.health_report[i].jitter, self.health_report[i].latency.variance)
        # If no packet loss then sequence number = last sequence number + 1
        packetsLost = sequence_number - (self.basics[i].last_sequence_number + 1)
        # If packetsLost is negative then this usually indicates duplicate or
        # out of order frame.
        self.health_report[i].packetLoss += packetsLost if packetsLost > 0 else 0
        
        self.calculate(
            self.health_report[i].goodput, (packet_size * 8) / ellapsedSeconds)

        self.basics[i].last_message_time = now
        self.basics[i].last_sequence_number = sequence_number

    def reset(self):
        for i in range(self.size):
            self.health_report[i] = NodeReport(
                0.0,
                HealthCore(0, float('inf'), -float('inf'), 0.0, 0.0, 0.0),
                HealthCore(0, float('inf'), -float('inf'), 0.0, 0.0, 0.0),
                HealthCore(0, float('inf'), -float('inf'), 0.0, 0.0, 0.0),
            )

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


class HealthReport:
    def __init__(self, _num_members: int) -> None:
        self.report = NodeReport * _num_members
        self._members = range(_num_members)
        zero_matrix = [[0.0] * _num_members] * _num_members
        base_frame = DataFrame(
            zero_matrix, columns=self._members, index=self._members)
        base_dict = {
            "count": base_frame.copy(deep=True),
            "min": base_frame.copy(deep=True),
            "max": base_frame.copy(deep=True),
            "mean": base_frame.copy(deep=True),
            "variance": base_frame.copy(deep=True),
            "sumOfSquaredDifferences": base_frame.copy(deep=True)
        }
        self.packet_loss = base_frame.copy(deep=True)
        self.latency = copy.deepcopy(base_dict)
        self.jitter = copy.deepcopy(base_dict)
        self.goodput = copy.deepcopy(base_dict)

    def __update(self, measure: Dict[str, DataFrame], index: Tuple[int, int], reported: HealthCore) -> None:
        measure["count"].loc[index[0], index[1]] = reported.count
        measure["min"].loc[index[0], index[1]] = reported.min
        measure["max"].loc[index[0], index[1]] = reported.max
        measure["mean"].loc[index[0], index[1]] = reported.mean
        measure["variance"].loc[index[0], index[1]] = reported.variance
        measure["sumOfSquaredDifferences"].loc[index[0],
                                               index[1]] = reported.sumOfSquaredDifferences

    def update(self, index: int, report):
        for i in self._members:
            self.packet_loss.loc[index, i] = report[i].packetLoss
            self.__update(self.latency, (index, i), report[i].latency)
            self.__update(self.jitter, (index, i), report[i].jitter)
            self.__update(self.goodput, (index, i), report[i].goodput)
