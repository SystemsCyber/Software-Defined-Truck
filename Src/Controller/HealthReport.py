from time import time
from typing import NamedTuple
from pandas import DataFrame
from Controller import COMMBlock


class HealthReport:
    def __init__(self, _members: list) -> None:
        self.members = _members
        zero_matrix = [[0] * len(_members)] * len(_members)
        self.packet_loss = DataFrame(
            zero_matrix, columns=_members, index=_members),
        self.latency = DataFrame(
            zero_matrix, columns=_members, index=_members),
        self.jitter = DataFrame(
            zero_matrix, columns=_members, index=_members),
        self.throughput = DataFrame(
            zero_matrix, columns=_members, index=_members)

    


class HealthBasics(NamedTuple):
    last_message_time = time()
    last_sequence_number = 0
    M2 = 0.0


class HealthCore(NamedTuple):
    count = 0
    min = float('inf')
    max = -float('inf')
    mean = 0.0
    variance = 0.0
    M2 = 0.0


class NodeReport(NamedTuple):
    packetLoss = 0.0
    latency = HealthCore()
    jitter = HealthCore()
    throughput = HealthCore()


class NetworkStats:
    def __init__(self, _id: int, _num_members: int) -> None:
        self.id = _id
        self.basics = [HealthBasics()] * len(_num_members)
        self.health_report = [NodeReport()] * len(_num_members)

    def update(self, msg: COMMBlock, packet_size: int):
        index = self.members.index(msg.id)
        node = self.health_report[index]
        basics = self.basics[index]
        now = time()
        basics.count += 1
        self.calculate(node.latency, basics.count, now - msg.timestamp)
        self.calculate(node.jitter, basics.count, node.latency.variance)
        node.packetLoss = (
            (msg.sequence_number - basics.count) / msg.sequence_number) * 100
        ellapsedSeconds = (now - basics.last_message_time) / 1000
        self.calculate(node.throughput, basics.count,
                       (packet_size * 8) / ellapsedSeconds)
        basics.last_message_time = now

    def calculate(edge: HealthCore, count: int, n: float):
        # From: https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance#Welford's_online_algorithm
        edge.min = min(edge.min, n)
        edge.max = max(edge.max, n)
        delta = n - edge.mean
        edge.mean += delta / count
        delta2 = n - edge.mean
        edge.M2 += delta * delta2
        edge.variance = edge.M2 / count
