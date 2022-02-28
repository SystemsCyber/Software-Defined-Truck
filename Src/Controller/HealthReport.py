import copy
import multiprocessing as mp
from ctypes import Structure, c_float, c_uint32
from dataclasses import dataclass
from queue import Empty
from time import sleep
from turtle import right
from types import SimpleNamespace
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib import animation
from matplotlib.widgets import Button
from pandas import DataFrame

from SensorNode import Member_Node
from Time_Client import Time_Client

from mpl_toolkits.axes_grid1 import make_axes_locatable


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


class NetworkMatrix:
    def __init__(self) -> None:
        self._members = range(4)
        zero_matrix = [[0.0] * 4] * 4
        self._base_frame = DataFrame(
            zero_matrix,
            columns=self.__create_axis_names(4),
            index=self.__create_axis_names(4)
        )
        base_dict = {
            "count": self._base_frame.copy(deep=True),
            "min": self._base_frame.copy(deep=True),
            "max": self._base_frame.copy(deep=True),
            "mean": self._base_frame.copy(deep=True),
            "variance": self._base_frame.copy(deep=True),
            "sumOfSquaredDifferences": self._base_frame.copy(deep=True)
        }
        self._last_report = SimpleNamespace(
            sim_frames=0,
            can_frames=0,
            dropped_sim_frames=0,
            dropped_can_frames=0,
            packet_loss=self._base_frame.copy(deep=True),
            latency=copy.deepcopy(base_dict),
            jitter=copy.deepcopy(base_dict),
            goodput=copy.deepcopy(base_dict)
        )
        self.current_stat = "packetLoss"

    def __create_axis_names(self, _num_members: int) -> list:
        axis_names = ["Controller"]
        for i in range(_num_members - 1):
            axis_names.append(f"SSSF{i}")
        return axis_names

    def __update_totals(self, r, ax):
        fs = 14
        ax.cla()
        ax.set_title("Totals", fontdict={
            'fontsize': 14, 'fontweight': 'bold'})
        ax.set(xlim=(0, 1), ylim=(0, 1), xticklabels=[], yticklabels=[], xlabel=None, ylabel=None, aspect=1)
        ax.set_axis_off()

        ax.text(0, .85, "Simulator", fontsize=fs)
        ax.text(.1, .7, "Count:", fontsize=fs)
        ax.text(1, .7, f"{r.sim_frames}", ha='right', fontsize=fs)
        ax.text(.1, .55, "Dropped:", fontsize=fs)
        ax.text(1, .55, f"{r.dropped_sim_frames}", ha='right', fontsize=fs)

        ax.text(0, .35, "CAN", fontsize=fs)
        ax.text(.1, .2, "Count:", fontsize=fs)
        ax.text(1, .2, f"{r.can_frames}", ha='right', fontsize=fs)
        ax.text(.1, .05, "Dropped:", fontsize=fs)
        ax.text(1, .05, f"{r.dropped_can_frames}", ha='right', fontsize=fs)
        return ax

    def __update_matrix(self, data, axes, cmap: str, title: str):
        axes[0].cla()
        axes[1].cla()
        axes[0].set_title(title, fontdict={
            'fontsize': 14, 'fontweight': 'bold'})
        return sns.heatmap(
            data,
            annot=True,
            robust=True,
            square=True,
            xticklabels="auto",
            yticklabels="auto",
            cbar=True,
            cbar_ax=axes[1],
            ax=axes[0],
            cmap=cmap
        )

    def __update_individual(self, r):
        axes = (self.ax, self.cbar_ax)
        if self.current_stat == "packetLoss":
            return (self.__update_matrix(
                r.packet_loss, axes, "rocket_r", "Packet Loss"),)
        elif self.current_stat == "latency":
            return (self.__update_matrix(
                r.latency["mean"], axes, "rocket_r", "Latency (msec)"),)
        elif self.current_stat == "jitter":
            return (self.__update_matrix(
                r.jitter["mean"], axes, "rocket_r", "Jitter (msec)"),)
        elif self.current_stat == "goodput":
            return (self.__update_matrix(
                r.goodput["mean"]/1000.0, axes, "rocket", "Goodput (Mb/s)"),)
        elif self.current_stat == "totals":
            self.cbar_ax.cla()
            return (self.__update_totals(r, self.ax),)

    def __update_other(self, r):
        ax = self.__update_matrix(
            r.packet_loss, (self.ax, self.cbar_ax), "rocket_r", "Packet Loss")
        ax1 = self.__update_matrix(
            r.latency["mean"], (self.ax1, self.cbar_ax1), "rocket_r", "Latency (msec)")
        ax2 = self.__update_matrix(
            r.jitter["mean"], (self.ax2, self.cbar_ax2), "rocket_r", "Jitter (msec)")
        ax3 = self.__update_matrix(
            r.goodput["mean"]/1000.0, (self.ax3, self.cbar_ax3), "rocket", "Goodput (Mb/s)")
        ax4 = self.__update_totals(r, self.ax4)
        return (ax, ax1, ax2, ax3, ax4)

    def __update(self, frame):
        report = self._last_report
        try:
            report = self._queue.get_nowait()
        except Empty:
            pass
        else:
            self._last_report = report
        finally:
            if self.display_mode == "individual":
                return self.__update_individual(report)
            else:
                return self.__update_other(report)

    def __display_packet_loss(self, event):
        self.current_stat = "packetLoss"

    def __display_latency(self, event):
        self.current_stat = "latency"

    def __display_jitter(self, event):
        self.current_stat = "jitter"

    def __display_goodput(self, event):
        self.current_stat = "goodput"
    
    def __display_totals(self, event):
        self.current_stat = "totals"

    def __create_button(self, axes: Tuple, name: str, on_click) -> Button:
        ax = self.fig.add_axes(axes)
        button = Button(ax, name)
        button.on_clicked(on_click)
        button.label.set_fontsize(12)
        return button

    def __create_cbar_ax(self, ax):
        divider = make_axes_locatable(ax)
        cbar_ax = divider.new_horizontal(size="5%", pad=0.05)
        self.fig.add_axes(cbar_ax)
        return cbar_ax

    def __animate(self, queue: mp.Queue, display_mode="grouped"):
        self._queue = queue
        self.display_mode = display_mode
        sns.set(font_scale=1.2)
        sns.set_style('white')
        if display_mode == "individual":
            self.fig, ax = plt.subplots()
            self.ax, self.cbar_ax = (ax, self.__create_cbar_ax(ax))
            self.packetLoss_button = self.__create_button(
                (0.15, 0.025, 0.15, 0.04), "Packet Loss", self.__display_packet_loss)
            self.latency_button = self.__create_button(
                (0.3, 0.025, 0.15, 0.04), "Latency", self.__display_latency)
            self.jitter_button = self.__create_button(
                (0.45, 0.025, 0.15, 0.04), "Jitter", self.__display_jitter)
            self.goodput_button = self.__create_button(
                (0.6, 0.025, 0.15, 0.04), "Goodput", self.__display_goodput)
            self.totals_button = self.__create_button(
                (0.75, 0.025, 0.15, 0.04), "Totals", self.__display_totals)
            plt.subplots_adjust(left=0.05, bottom=0.25)
        elif display_mode == "vertical":
            grid_kws = {'hspace': 0.4}
            self.fig, axes = plt.subplots(5, 1, gridspec_kw=grid_kws)
            self.ax, self.cbar_ax = (axes[0], self.__create_cbar_ax(axes[0]))
            self.ax1, self.cbar_ax1 = (axes[1], self.__create_cbar_ax(axes[1]))
            self.ax2, self.cbar_ax2 = (axes[2], self.__create_cbar_ax(axes[2]))
            self.ax3, self.cbar_ax3 = (axes[3], self.__create_cbar_ax(axes[3]))
            self.ax4 = axes[4]
            plt.subplots_adjust(left=0.05, right=0.98, bottom=0, top=0.96)
        elif display_mode == "horizontal":
            grid_kws = {'wspace': 0.4}
            self.fig, axes = plt.subplots(1, 5, gridspec_kw=grid_kws)
            self.ax, self.cbar_ax = (axes[0], self.__create_cbar_ax(axes[0]))
            self.ax1, self.cbar_ax1 = (axes[1], self.__create_cbar_ax(axes[1]))
            self.ax2, self.cbar_ax2 = (axes[2], self.__create_cbar_ax(axes[2]))
            self.ax3, self.cbar_ax3 = (axes[3], self.__create_cbar_ax(axes[3]))
            self.ax4 = axes[4]
            plt.subplots_adjust(left=0.05, right=0.98, bottom=0.05, top=1)
        elif display_mode == "grouped":
            grid_kws = {'wspace': 0.4, 'hspace': 0.1}
            self.fig, axes = plt.subplots(2, 3, gridspec_kw=grid_kws)
            self.ax, self.cbar_ax = (axes[0][0], self.__create_cbar_ax(axes[0][0]))
            self.ax1, self.cbar_ax1 = (axes[0][1], self.__create_cbar_ax(axes[0][1]))
            self.ax2, self.cbar_ax2 = (axes[1][0], self.__create_cbar_ax(axes[1][0]))
            self.ax3, self.cbar_ax3 = (axes[1][1], self.__create_cbar_ax(axes[1][1]))
            self.ax4 = axes[0][2]
            axes[1][2].set_axis_off()
            plt.subplots_adjust(left=0.05, right=0.98, bottom=0.05, top=0.98)

        self.anim = animation.FuncAnimation(
            self.fig, self.__update, blit=True, repeat=False)
        mng = plt.get_current_fig_manager()
        mng.set_window_title("Network Statistics")
        plt.show()

    def animate(self, queue: mp.Queue, display_mode="grouped"):
        try:
            self.__animate(queue, display_mode)
        except (OSError, ValueError):
            self.anim.event_source.stop()
            plt.close(self.fig)
            return


# def create_random_values(report):
#     report.packet_loss.iloc[0, 0] = 0.0
#     report.packet_loss.iloc[0, 1] = np.random.random() * 10
#     report.packet_loss.iloc[1, 0] = np.random.random() * 10
#     report.packet_loss.iloc[1, 1] = 0.0
#     report.latency["mean"].iloc[0, 0] = 0.0
#     report.latency["mean"].iloc[0, 1] = np.random.random() * 10
#     report.latency["mean"].iloc[1, 0] = np.random.random() * 10
#     report.latency["mean"].iloc[1, 1] = 0.0
#     report.jitter["mean"].iloc[0, 0] = 0.0
#     report.jitter["mean"].iloc[0, 1] = np.random.random() * 10
#     report.jitter["mean"].iloc[1, 0] = np.random.random() * 10
#     report.jitter["mean"].iloc[1, 1] = 0.0
#     report.goodput["mean"].iloc[0, 0] = 0.0
#     report.goodput["mean"].iloc[0, 1] = np.random.random() * 50
#     report.goodput["mean"].iloc[1, 0] = np.random.random() * 50
#     report.goodput["mean"].iloc[1, 1] = 0.0
#     return SimpleNamespace(
#         sim_frames=report.sim_frames,
#         can_frames=report.can_frames,
#         dropped_sim_frames=report.dropped_sim_frames,
#         dropped_can_frames=report.dropped_can_frames,
#         packet_loss=report.packet_loss,
#         latency=report.latency,
#         jitter=report.jitter,
#         goodput=report.goodput
#     )


# if __name__ == "__main__":
#     health_queue = mp.Queue()
#     health_report = HealthReport(2)
#     matrix = NetworkMatrix()
#     matrix_thread = mp.Process(
#         target=matrix.animate, args=(health_queue, "individual"), daemon=True)
#     matrix_thread.start()
#     while True:
#         try:
#             health_report.sim_frames += np.random.randint(50, 70)
#             health_report.can_frames += np.random.randint(200, 280)
#             health_report.dropped_sim_frames += np.random.randint(0, 5)
#             health_report.dropped_can_frames += np.random.randint(0, 5)
#             health_queue.put(create_random_values(health_report))
#             sleep(1)
#         except KeyboardInterrupt:
#             break
