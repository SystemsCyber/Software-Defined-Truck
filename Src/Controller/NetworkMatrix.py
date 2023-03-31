from __future__ import annotations
import logging
import copy
import multiprocessing as mp
from multiprocessing.synchronize import Event
from time import sleep, time
from types import SimpleNamespace
from typing import Tuple

import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib import animation
from matplotlib.widgets import Button
from mpl_toolkits.axes_grid1 import make_axes_locatable
from pandas import DataFrame

from Environment import CANLayLogger
from CANLayTUI import TUIOutput as TO


class NetworkMatrix:
    def __init__(self, num_members: int, labels: list[str]) -> None:
        self.current_stat = "packetLoss"
        self.num_members = num_members
        zero_matrix = [[0.0] * num_members] * num_members
        historical_matrix = [[[0.0] * 8] * num_members] * num_members
        # self._base_frame = DataFrame(zero_matrix, columns=list(reversed(labels)), index=labels)
        self._base_frame = DataFrame(zero_matrix, columns=labels, index=labels)
        self._reports = SimpleNamespace(
            packetLoss=copy.deepcopy(historical_matrix),
            latency=copy.deepcopy(historical_matrix),
            jitter=copy.deepcopy(historical_matrix),
            goodput=copy.deepcopy(historical_matrix)
        )
        self._predict = SimpleNamespace(
            packetLoss= self._base_frame.copy(deep=True),
            latency=self._base_frame.copy(deep=True),
            jitter=self._base_frame.copy(deep=True),
            goodput=self._base_frame.copy(deep=True)
        )
        self._current_rotation = 0
        self._current_member = 0

    def __update_totals(self, ax):
        fs = 12
        ax.cla()
        ax.set_title("Totals", fontdict={
            'fontsize': 14, 'fontweight': 'bold'})
        ax.set(xlim=(0, 1), ylim=(0, 1), xticklabels=[], yticklabels=[], xlabel=None, ylabel=None, aspect=1)
        ax.set_axis_off()
        with self._lock:
            ax.text(0, .9, "Simulator", fontsize=fs, fontweight="bold")
            ax.text(.1, .79, "Count:", fontsize=fs)
            ax.text(1, .79, f"{self._counts.sim_frames}", ha='right', fontsize=fs)
            ax.text(.1, .68, "Dropped:", fontsize=fs)
            ax.text(1, .68, f"{self._counts.dropped_sim_frames}", ha='right', fontsize=fs)
            ax.text(.1, .57, "Retrans:", fontsize=fs)
            ax.text(1, .57, f"{self._counts.sim_retrans}", ha='right', fontsize=fs)

            ax.text(0, .35, "CAN", fontsize=fs, fontweight="bold")
            ax.text(.1, .24, "Count:", fontsize=fs)
            ax.text(1, .24, f"{self._counts.can_frames}", ha='right', fontsize=fs)
            ax.text(.1, .13, "Dropped:", fontsize=fs)
            ax.text(1, .13, f"{self._counts.dropped_can_frames}", ha='right', fontsize=fs)
        return ax

    def __update_matrix(self, data, axes, cmap: str, title: str, vmin, vmax):
        axes[0].cla()
        axes[0].set_title(title, fontdict={
            'fontsize': 14, 'fontweight': 'bold'})
        return sns.heatmap(
            data,
            vmin=vmin,
            vmax=vmax,
            annot=True,
            # robust=True,
            square=True,
            xticklabels="auto",
            yticklabels="auto",
            cbar=True,
            cbar_ax=axes[1],
            ax=axes[0],
            cmap=cmap
        )

    def __update_individual(self):
        axes = (self.ax, self.cbar_ax)
        if self.current_stat == "packetLoss":
            return (self.__update_matrix(self._predict.packetLoss,
                axes, "rocket_r", "Packet Loss", 0, 10),)
        elif self.current_stat == "latency":
            return (self.__update_matrix(self._predict.latency,
                axes, "rocket_r", "Latency (msec)", 0, 10),)
        elif self.current_stat == "jitter":
            return (self.__update_matrix(self._predict.jitter,
                axes, "rocket_r", "Jitter (msec)", 0, 10),)
        elif self.current_stat == "goodput":
            return (self.__update_matrix(self._predict.goodput/1000.0,
                axes, "rocket", "Goodput (Mb/s)", 0, 10),)
        elif self.current_stat == "totals":
            self.cbar_ax.cla()
            return (self.__update_totals(self.ax),)

    def __update_other(self):
        ax = self.__update_matrix(self._predict.packetLoss,
            (self.ax, self.cbar_ax), "rocket_r", "Packet Loss", 0, 10)
        ax1 = self.__update_matrix(self._predict.latency,
            (self.ax1, self.cbar_ax1), "rocket_r", "Latency (msec)", 0, 10)
        ax2 = self.__update_matrix(self._predict.jitter,
            (self.ax2, self.cbar_ax2), "rocket_r", "Jitter (msec)", 0, 10)
        ax3 = self.__update_matrix(self._predict.goodput/1000.0,
            (self.ax3, self.cbar_ax3), "rocket", "Goodput (Mb/s)", 0, 10)
        if self.display_totals:
            ax4 = self.__update_totals(self.ax4)
            return (ax, ax1, ax2, ax3, ax4)
        else:
            return (ax, ax1, ax2, ax3)

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
        button = Button(ax, name) # type: ignore
        button.on_clicked(on_click)
        button.label.set_fontsize(12) # type: ignore
        return button

    def __create_cbar_ax(self, ax):
        divider = make_axes_locatable(ax)
        cbar_ax = divider.new_horizontal(size="5%", pad=0.05)
        self.fig.add_axes(cbar_ax)
        return cbar_ax

    def __animate_individual(self):
        self.fig, ax = plt.subplots()
        self.ax, self.cbar_ax = (ax, self.__create_cbar_ax(ax))
        screen_shift = 5
        num_buttons = 5 if self.display_totals else 4
        start = (100//num_buttons)
        if self.display_totals:
            start -= int(2*screen_shift)
        else:
            start -= int(1.2 * screen_shift)
        stop = (100 - start) if (start % 2 == 1) else 100
        ax_start = [(i/100) for i in range(start, stop, 15)]
        ax_other = (0.025, 0.15, 0.04)

        self.packetLoss_button = self.__create_button(
            (ax_start[0], *ax_other), "Packet Loss", self.__display_packet_loss)
        self.latency_button = self.__create_button(
            (ax_start[1], *ax_other), "Latency", self.__display_latency)
        self.jitter_button = self.__create_button(
            (ax_start[2], *ax_other), "Jitter", self.__display_jitter)
        self.goodput_button = self.__create_button(
            (ax_start[3], *ax_other), "Goodput", self.__display_goodput)
        if self.display_totals:
            self.totals_button = self.__create_button(
                (ax_start[4], *ax_other), "Totals", self.__display_totals)
        plt.subplots_adjust(left=screen_shift/100, bottom=0.25)

    def __animate_vertical(self):
        b = 0 if self.display_totals else 0.05
        grid_kws = {'hspace': 0.4}
        rows_cols = (5, 1) if self.display_totals else (4, 1)
        self.fig, axes = plt.subplots(*rows_cols, gridspec_kw=grid_kws) # type: ignore
        axes: list[plt.Axes]
        self.ax, self.cbar_ax = (axes[0], self.__create_cbar_ax(axes[0]))
        self.ax1, self.cbar_ax1 = (axes[1], self.__create_cbar_ax(axes[1]))
        self.ax2, self.cbar_ax2 = (axes[2], self.__create_cbar_ax(axes[2]))
        self.ax3, self.cbar_ax3 = (axes[3], self.__create_cbar_ax(axes[3]))
        if self.display_totals:
            self.ax4 = axes[4]
        plt.subplots_adjust(left=0.05, right=0.98, bottom=b, top=0.96)

    def __animate_horizontal(self):
        r = 0.98 if self.display_totals else 0.95
        grid_kws = {'wspace': 0.5}
        rows_cols = (1, 5) if self.display_totals else (1, 4)
        self.fig, axes = plt.subplots(*rows_cols, gridspec_kw=grid_kws) # type: ignore
        axes: list[plt.Axes]
        self.ax, self.cbar_ax = (axes[0], self.__create_cbar_ax(axes[0]))
        self.ax1, self.cbar_ax1 = (axes[1], self.__create_cbar_ax(axes[1]))
        self.ax2, self.cbar_ax2 = (axes[2], self.__create_cbar_ax(axes[2]))
        self.ax3, self.cbar_ax3 = (axes[3], self.__create_cbar_ax(axes[3]))
        if self.display_totals:
            self.ax4 = axes[4]
        plt.subplots_adjust(left=0.05, right=r, bottom=0.05, top=1)

    def __animate_grouped(self):
        hspace = 0.1 if self.display_totals else 0.3
        rt = 0.98 if self.display_totals else 0.94
        lb = 0.05 if self.display_totals else 0.09
        grid_kws = {'wspace': 0.4, 'hspace': hspace}
        rows_cols = (2, 3) if self.display_totals else (2, 2)
        self.fig, axes = plt.subplots(*rows_cols, gridspec_kw=grid_kws) # type: ignore
        axes: list[list[plt.Axes]]
        self.ax, self.cbar_ax = (axes[0][0], self.__create_cbar_ax(axes[0][0]))
        self.ax1, self.cbar_ax1 = (axes[0][1], self.__create_cbar_ax(axes[0][1]))
        self.ax2, self.cbar_ax2 = (axes[1][0], self.__create_cbar_ax(axes[1][0]))
        self.ax3, self.cbar_ax3 = (axes[1][1], self.__create_cbar_ax(axes[1][1]))
        if self.display_totals:
            self.ax4 = axes[0][2]
            axes[1][2].set_axis_off()
        plt.subplots_adjust(left=lb, right=rt, bottom=lb, top=rt)

    def __rotate(self, l, n):
        return l[n:] + l[:n]

    def __ema(self, points):
        alpha = 2 / (len(points) + 1)
        # initialize the exponential moving average
        moving_average = [points[0]]

        # loop through the points and calculate the moving average
        for i in range(1, len(points)):
            moving_average.append(
                alpha * points[i] + (1 - alpha) * moving_average[i - 1])

        return moving_average[-1]

    def __update(self, frame):
        if self._stop_event.is_set():
            self.anim.event_source.stop() # type: ignore
            return
        with self._lock:
            index = self._current_member % self.num_members
            k = self._current_rotation % 8
            for i in range(self.num_members):
                self._reports.packetLoss[index][i][k] = self._report[index][i].packetLoss
                self._predict.packetLoss.iloc[index,i] = self.__ema(
                    self.__rotate(self._reports.packetLoss[index][i], k))
                self._reports.latency[index][i][k] = self._report[index][i].latency.mean
                self._predict.latency.iloc[index,i] = self.__ema(
                    self.__rotate(self._reports.latency[index][i], k))
                self._reports.jitter[index][i][k] = self._report[index][i].jitter.mean
                self._predict.jitter.iloc[index,i] = self.__ema(
                    self.__rotate(self._reports.jitter[index][i], k))
                self._reports.goodput[index][i][k] = self._report[index][i].goodput.mean
                self._predict.goodput.iloc[index,i] = self.__ema(
                    self.__rotate(self._reports.goodput[index][i], k))
            self._current_member += 1
            if self._current_member % self.num_members == 0:
                self._current_member = 0
                self._current_rotation += 1
            # for i in range(self.num_members):
            #     for j in range(self.num_members):
            #         logging.info(
            #             f"Node {i} Member{j}: \n"
            #             f"packetLoss: {self._report[i][j].packetLoss}\n"
            #             f"latency: {self._report[i][j].latency.mean}\n"
            #             f"jitter: {self._report[i][j].jitter.mean}\n"
            #             f"goodput: {self._report[i][j].goodput.mean}")
            try:
                self._output.put((TO.TOTAL_STATS, 
                    (self._counts.sim_frames, self._counts.dropped_sim_frames,
                    self._counts.sim_retrans,
                    self._counts.can_frames,
                    self._counts.dropped_can_frames)))
            except EOFError:
                self.anim.event_source.stop() # type: ignore
                return
        if self.display_mode == "individual":
            return self.__update_individual()
        else:
            return self.__update_other()

    # # Just for paper
    # def __temp_update(self, frame):
    #     report = self._last_report
    #     try:
    #         report = self._queue.get_nowait()
    #     except Empty:
    #         pass
    #     else:
    #         self._last_report = report
    #     finally:
    #         # self.ax.cla()
    #         self.can_rate.append(report.can_frames - self.last_can_frames)
    #         self.last_can_frames = report.can_frames
    #         # min_val = min(report.can_timestamps)
    #         # max_val = max(report.can_timestamps)
    #         return self.ax.plot(self.can_rate),
    #         # self.ax.set_title("CAN Traffic", fontdict={
    #         #     'fontsize': 14, 'fontweight': 'bold'})
    #         # print(report.can_timestamps)
    #         # return plt.plot(
    #         #     report.can_timestamps # type: ignore
    #         #     # annot=True,
    #         #     # robust=True,
    #         #     # square=True,
    #         #     # xticklabels="auto",
    #         #     # yticklabels="auto",
    #         #     # ax=self.ax
    #         # ),

    def animate(
            self,
            lock,
            stop_event: Event,
            report,
            counts,
            output: mp.Queue,
            log_queue: mp.Queue,
            log_level: int,
            display_mode="grouped",
            display_totals=False
        ):
        # Matplotlib prints a LOT of debug messages
        if log_level == logging.DEBUG:
            log_level = logging.INFO
        CANLayLogger.worker_configure(log_queue, log_level)
        try:
            self._lock = lock
            self._stop_event = stop_event
            self._report = report
            self._counts = counts
            self._output = output
            self.display_mode = display_mode
            self.display_totals = display_totals
            sns.set(font_scale=1.2)
            sns.set_style('white')
            if display_mode == "individual":
                self.__animate_individual()
            elif display_mode == "vertical":
                self.__animate_vertical()
            elif display_mode == "horizontal":
                self.__animate_horizontal()
            elif display_mode == "grouped":
                self.__animate_grouped()
            # Just for the paper but eventually swtich to just matplot lib:
            #   https://stackoverflow.com/questions/45697522/seaborn-heatmap-plotting-execution-time-optimization
            # and using tabs:
            #   https://github.com/astromancer/mpl-multitab
            # actually switch to plotext eventually. Its possible but you;ll need to manually add it most likely.
            # self.fig, self.ax = plt.subplots(1, 1)
            # self.can_rate = []
            # self.last_can_frames = 0
            # self.ln = self.ax.plot([])[0]
            self.anim = animation.FuncAnimation(
                self.fig, self.__update, frames=None, interval=1000/self.num_members, blit=True, repeat=False)
            # self.anim = animation.FuncAnimation(
            #     self.fig, self.__temp_update, frames=None, interval=1000, repeat=False)
            mng = plt.get_current_fig_manager()
            mng.set_window_title("Network Statistics")
            # mng.set_window_title("CAN Traffic")
            plt.ioff()
            plt.show()
        except Exception as e:
            logging.error(e, exc_info=True)
        finally:
            if self.anim.event_source: # type: ignore
                self.anim.event_source.stop() # type: ignore
            plt.close(self.fig)


# from SensorNode import Member_Node
# import numpy as np
# from HealthReport import HealthReport
# import ctypes as ct
# from HealthReport import NodeReport

# def create_random_values(report, can_timestamps):
#     global last_timestamp
#     report.packetLoss.iloc[0, 0] = 0.0
#     report.packetLoss.iloc[0, 1] = np.random.randint(0,2)
#     report.packetLoss.iloc[1, 0] = np.random.randint(0,2)
#     report.packetLoss.iloc[1, 1] = 0.0
#     report.latency["mean"].iloc[0, 0] = 0.0
#     report.latency["mean"].iloc[0, 1] = np.random.random()
#     report.latency["mean"].iloc[1, 0] = np.random.random()
#     report.latency["mean"].iloc[1, 1] = 0.0
#     report.jitter["mean"].iloc[0, 0] = 0.0
#     report.jitter["mean"].iloc[0, 1] = np.random.random()
#     report.jitter["mean"].iloc[1, 0] = np.random.random()
#     report.jitter["mean"].iloc[1, 1] = 0.0
#     report.goodput["mean"].iloc[0, 0] = 0.0
#     report.goodput["mean"].iloc[0, 1] = np.random.randint(50000, 60000)
#     report.goodput["mean"].iloc[1, 0] = np.random.randint(40000, 50000)
#     report.goodput["mean"].iloc[1, 1] = 0.0
#     for i in range(np.random.randint(0, 1000)):
#         last_timestamp = last_timestamp + np.random.randint(0, 100)
#         can_timestamps.append(last_timestamp)
#     return SimpleNamespace(
#         sim_frames=report.sim_frames,
#         can_frames=report.can_frames,
#         sim_retrans=np.random.randint(50, 70),
#         dropped_sim_frames=report.dropped_sim_frames,
#         dropped_can_frames=report.dropped_can_frames,
#         packetLoss=report.packetLoss,
#         latency=report.latency,
#         jitter=report.jitter,
#         goodput=report.goodput,
#         # just for paper
#         can_timestamps=can_timestamps
#     )

# def generate_random_members(num_members: int) -> list[Member_Node]:
#     members = []
#     for i in range(num_members):
#         members.append(Member_Node(i, [{"Type": "CAN", "ID": "0x123", "Name": "Test"}]))
#     return members


# if __name__ == "__main__":
#     can_timestamps = []
#     global last_timestamp
#     last_timestamp = 0
#     stop_event = mp.Event()
#     output = mp.Queue()
#     log_queue = mp.Queue()
#     health_report = HealthReport(generate_random_members(3))
#     health_report.start_display(stop_event, output, log_queue, logging.DEBUG)
#     report = ct.Array(NodeReport, 3)
#     index = 0
#     msg_num = 0
#     while True:
#         try:
#             for i in range(3):
#                 report[i].packetLoss = np.random.randint(0, 2)
#                 report[i].latency = np.random.random()
#                 report[i].jitter = np.random.random()
#                 report[i].goodput = np.random.randint(50000, 60000)
#             health_report.update(index, report, ct.c_uint32(msg_num))
#             index = (index + 1) % 3
#             msg_num += np.random.randint(0, 100)
#             sleep(1)
#         except KeyboardInterrupt:
#             break
#     stop_event.set()
#     health_report.stop_display()
