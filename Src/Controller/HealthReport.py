from ctypes import *
from collections import namedtuple
from time import time
from pandas import DataFrame
from SensorNode import COMMBlock


class HealthBasics(namedtuple):
    last_message_time = time()
    last_sequence_number = 0

class HealthCore(Structure):
    _pack_ = 4
    _fields_ = [
        ("count", c_uint32),
        ("min", c_float),
        ("max", c_float),
        ("mean", c_float),
        ("variance", c_float),
        ("sumofSquaredDifferences", c_float)
    ]

    def __repr__(self) -> str:
        return (
            f'\tCount: {self.count} Min: {self.min} Max: {self.max}\n'
            f'\tMean: {self.mean} Variance: {self.variance}\n'
            f'\tSumofSquaredDifferences: {self.sumofSquaredDifferences}\n'
            )
    # min = float('inf')
    # max = -float('inf')


class NodeReport(Structure):
    _pack_ = 4
    _fields = [
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
    def __init__(self, _num_members: int) -> None:
        self.size = _num_members
        self.basics = [HealthBasics()] * _num_members
        self.health_report = [NodeReport(
            0.0,
            HealthCore(0, float('inf'), -float('inf'), 0.0, 0.0, 0.0),
            HealthCore(0, float('inf'), -float('inf'), 0.0, 0.0, 0.0),
            HealthCore(0, float('inf'), -float('inf'), 0.0, 0.0, 0.0),
            )] * _num_members

    def update(self, i: int, packet_size: int, timestamp: int, sequence_number: int):
        now = time()
        sequence_offset = sequence_number - self.basics[i].last_sequence_number
        ellapsedSeconds = (now - self.basics[i].last_message_time) / 1000

        self.calculate(self.health_report[i].latency, now - timestamp)
        self.calculate(self.health_report.jitter, self.health_report[i].variance)
        self.health_report[i].packetLoss = sequence_offset - self.health_report[i].latency.count
        self.calculate(self.health_report[i].goodput, (packet_size * 8) / ellapsedSeconds)

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

    def calculate(edge: HealthCore, n: float):
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
        self.members = range(_num_members)
        zero_matrix = [[0] * _num_members] * _num_members
        self.packet_loss = DataFrame(
            zero_matrix, columns=self.members, index=self.members)
        self.latency = DataFrame(
            zero_matrix, columns=self.members, index=self.members)
        self.jitter = DataFrame(
            zero_matrix, columns=self.members, index=self.members)
        self.throughput = DataFrame(
            zero_matrix, columns=self.members, index=self.members)