from time import time
from typing import NamedTuple

class HealthBasics(NamedTuple):
    count = 0
    last_message_time = time()

class HealthCore(NamedTuple):
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
    def __init__(self, _id: int, _members: list) -> None:
        self.id = _id
        self.members = _members
        self.basics = [HealthBasics()] * len(_members)
        self.health_report = [NodeReport()] * len(_members)

    def update(self, id: int, packetSize: int, timestamp: int, sequence_number: int):
        for i in range(len(self.members)):
            if self.members[i] == id:
                node = self.health_report[i]
                basics = self.basics[i]
                now = time()
                basics.count += 1
                self.calculate(node.latency, basics.count, now - timestamp)
                self.calculate(node.jitter, basics.count, node.latency.variance)
                node.packetLoss = ((sequence_number - basics.count) / sequence_number) * 100
                ellapsedSeconds = (now - basics.last_message_time) / 1000
                self.calculate(node.throughput, basics.count, (packetSize * 8) / ellapsedSeconds)
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