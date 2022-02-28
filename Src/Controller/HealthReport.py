import copy
from ctypes import Structure, c_float, c_uint32
from dataclasses import dataclass
from typing import Dict, List, Tuple

from pandas import DataFrame

from SensorNode import Member_Node
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
        # if these numbers are zero then this is the first messages we've received
        if (self.basics[i].last_message_time != 0) and (self.basics[i].last_sequence_number != 0):
            # print(f'Controller Recv: {now} SSSF Send: {timestamp} Diff: {delay}')
            ellapsedSeconds = (now - self.basics[i].last_message_time) / 1000.0
            if ellapsedSeconds == 0.0:
                ellapsedSeconds = 0.0001  # Retransmission

            self.calculate(self.health_report[i].latency, abs(delay))
            self.calculate(
                self.health_report[i].jitter, self.health_report[i].latency.variance)
            # If no packet loss then sequence number = last sequence number + 1
            packetsLost = sequence_number - \
                (self.basics[i].last_sequence_number + 1)
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
    def __init__(self, _members: List[Member_Node]) -> None:
        _num_members = len(_members)
        self._members = _members
        self.report = NodeReport * _num_members
        zero_matrix = [[0.0] * _num_members] * _num_members
        base_frame = DataFrame(
            zero_matrix,
            columns=self.__create_axis_names(),
            index=self.__create_axis_names()
        )
        base_dict = {
            "count": base_frame.copy(deep=True),
            "min": base_frame.copy(deep=True),
            "max": base_frame.copy(deep=True),
            "mean": base_frame.copy(deep=True),
            "variance": base_frame.copy(deep=True),
            "sumOfSquaredDifferences": base_frame.copy(deep=True)
        }
        self.can_frames_per_device = [0] * _num_members
        self.sim_frames = 0
        self.can_frames = 0
        self.dropped_sim_frames = 0
        self.dropped_can_frames = 0
        self.packet_loss = base_frame.copy(deep=True)
        self.latency = copy.deepcopy(base_dict)
        self.jitter = copy.deepcopy(base_dict)
        self.goodput = copy.deepcopy(base_dict)

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

    def __update(self, measure: Dict[str, DataFrame], index: Tuple[int, int], reported: HealthCore) -> None:
        measure["count"].iloc[index[0], index[1]] = reported.count
        measure["min"].iloc[index[0], index[1]] = reported.min
        measure["max"].iloc[index[0], index[1]] = reported.max
        measure["mean"].iloc[index[0], index[1]] = reported.mean
        measure["variance"].iloc[index[0], index[1]] = reported.variance
        measure["sumOfSquaredDifferences"].iloc[index[0],
                                                index[1]] = reported.sumOfSquaredDifferences

    def update(self, index: int, report, last_msg_num: int):
        if index == 0:
            self.sim_frames = last_msg_num
        else:
            self.can_frames -= self.can_frames_per_device[index]
            self.can_frames += last_msg_num
            self.can_frames_per_device[index] = last_msg_num

        for i in range(len(self._members)):
            self.packet_loss.iloc[index, i] = report[i].packetLoss
            self.__update(self.latency, (index, i), report[i].latency)
            self.__update(self.jitter, (index, i), report[i].jitter)
            self.__update(self.goodput, (index, i), report[i].goodput)
            if i == 0:
                self.dropped_sim_frames += report[i].packetLoss
            else:
                self.dropped_can_frames += report[i].packetLoss
