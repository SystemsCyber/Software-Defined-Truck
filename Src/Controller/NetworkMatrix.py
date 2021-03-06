import copy
import multiprocessing as mp
from queue import Empty
from time import sleep
from types import SimpleNamespace
from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib import animation
from matplotlib.widgets import Button
from mpl_toolkits.axes_grid1 import make_axes_locatable
from pandas import DataFrame

from HealthReport import HealthReport


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
            sim_retrans=0,
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
        fs = 12
        ax.cla()
        ax.set_title("Totals", fontdict={
            'fontsize': 14, 'fontweight': 'bold'})
        ax.set(xlim=(0, 1), ylim=(0, 1), xticklabels=[], yticklabels=[], xlabel=None, ylabel=None, aspect=1)
        ax.set_axis_off()

        ax.text(0, .9, "Simulator", fontsize=fs, fontweight="bold")
        ax.text(.1, .79, "Count:", fontsize=fs)
        ax.text(1, .79, f"{r.sim_frames}", ha='right', fontsize=fs)
        ax.text(.1, .68, "Dropped:", fontsize=fs)
        ax.text(1, .68, f"{r.dropped_sim_frames}", ha='right', fontsize=fs)
        ax.text(.1, .57, "Retrans:", fontsize=fs)
        ax.text(1, .57, f"{r.sim_retrans}", ha='right', fontsize=fs)

        ax.text(0, .35, "CAN", fontsize=fs, fontweight="bold")
        ax.text(.1, .24, "Count:", fontsize=fs)
        ax.text(1, .24, f"{r.can_frames}", ha='right', fontsize=fs)
        ax.text(.1, .13, "Dropped:", fontsize=fs)
        ax.text(1, .13, f"{r.dropped_can_frames}", ha='right', fontsize=fs)
        return ax

    def __update_matrix(self, data, axes, cmap: str, title: str):
        axes[0].cla()
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
        if self.display_totals:
            ax4 = self.__update_totals(r, self.ax4)
            return (ax, ax1, ax2, ax3, ax4)
        else:
            return (ax, ax1, ax2, ax3)

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
        self.fig, axes = plt.subplots(*rows_cols, gridspec_kw=grid_kws)
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
        self.fig, axes = plt.subplots(*rows_cols, gridspec_kw=grid_kws)
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
        self.fig, axes = plt.subplots(*rows_cols, gridspec_kw=grid_kws)
        self.ax, self.cbar_ax = (axes[0][0], self.__create_cbar_ax(axes[0][0]))
        self.ax1, self.cbar_ax1 = (axes[0][1], self.__create_cbar_ax(axes[0][1]))
        self.ax2, self.cbar_ax2 = (axes[1][0], self.__create_cbar_ax(axes[1][0]))
        self.ax3, self.cbar_ax3 = (axes[1][1], self.__create_cbar_ax(axes[1][1]))
        if self.display_totals:
            self.ax4 = axes[0][2]
            axes[1][2].set_axis_off()
        plt.subplots_adjust(left=lb, right=rt, bottom=lb, top=rt)

    def __animate(self, queue: mp.Queue, display_mode="grouped", display_totals=False):
        self._queue = queue
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

        self.anim = animation.FuncAnimation(
            self.fig, self.__update, frames=None, interval=1000, blit=True, repeat=False)
        mng = plt.get_current_fig_manager()
        mng.set_window_title("Network Statistics")
        plt.show()

    def animate(self, queue: mp.Queue, display_mode="grouped", display_totals=False):
        try:
            self.__animate(queue, display_mode, display_totals)
        except (OSError, ValueError):
            self.anim.event_source.stop()
            plt.close(self.fig)
            return


# def create_random_values(report):
#     report.packet_loss.iloc[0, 0] = 0.0
#     report.packet_loss.iloc[0, 1] = np.random.randint(0,2)
#     report.packet_loss.iloc[1, 0] = np.random.randint(0,2)
#     report.packet_loss.iloc[1, 1] = 0.0
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
#     return SimpleNamespace(
#         sim_frames=report.sim_frames,
#         can_frames=report.can_frames,
#         sim_retrans=np.random.randint(50, 70),
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
#         target=matrix.animate, args=(health_queue, "grouped", True), daemon=True)
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
