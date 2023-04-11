import threading as th
from CANLay.Environment import OutputType as OT
import asyncio
import multiprocessing as mp
from multiprocessing.connection import PipeConnection
from concurrent.futures import ThreadPoolExecutor
import logging

from rich.pretty import pprint
from rich import print as rp
from rich.text import Text
from rich.table import Table
from rich.rule import Rule
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import (
    Footer, Header, Input, Static, TextLog, Placeholder, Label, DataTable)

class CommandLine(Container):
    def compose(self) -> ComposeResult:
        yield Static(">", classes="label")
        yield Input(placeholder="Enter a command...")

class Results(Container):
    def compose(self) -> ComposeResult:
        yield TextLog(id="results")
        # yield Placeholder(id="Results")

class LiveView(Container):
    def compose(self) -> ComposeResult:
        yield Label(" Statistics", classes="liveViewLabel")
        yield Static(id="totalStats", classes="totalStats", markup=True)
        # yield Placeholder(id="totalStats", classes="totalStats")
        yield Label(" Simulator Input", classes="liveViewLabel")
        yield Static(id="simLogs", classes="simLogs", markup=True)
        # yield Placeholder(id="simLogs", classes="simLogs")
        yield Label(" CAN Messages", classes="liveViewLabel")
        yield DataTable(id="canLogs", classes="canLogs")
        # yield Placeholder(id="canLogs", classes="canLogs")

live_can_data = []

class CANLayTUI(App):

    CSS_PATH = "client.css"
    TITLE = "CANLay"
    BINDINGS = [
        Binding("ctrl+c,ctrl+q", "app.quit", "Quit", show=True, priority=True),
        ("ctrl+l", "app.toggle_class('TextLog', '-hidden')", "Log"),
        ]

    def __init__(self,
        output_queue: mp.Queue,
        log_output_queue: mp.Queue,
        cmd_conn: PipeConnection,
        **kwargs):
        super().__init__(**kwargs)
        self.output_queue = output_queue
        self.log_output_queue = log_output_queue
        self.cmd_conn = cmd_conn
        self._tui_stop = mp.Event()
        self._executors = ThreadPoolExecutor(max_workers=2)
        self._event_loop = asyncio.get_event_loop()

    async def monitor_log_queue(self) -> None:
        logs: TextLog = self.query_one("#logViewer", TextLog)
        while not self._tui_stop.is_set():
            msg = await self._event_loop.run_in_executor(
                self._executors, self.log_output_queue.get)
            if msg is None:
                break
            else:
                logs.write(Text.from_markup(msg))

    async def monitor_output_queue(self) -> None:
        results: TextLog = self.query_one("#results", TextLog)
        simlogs: Static = self.query_one("#simLogs", Static)
        totalStats: Static = self.query_one("#totalStats", Static)
        while not self._tui_stop.is_set():
            msg = await self._event_loop.run_in_executor(
                self._executors, self.output_queue.get)
            if msg is None:
                break
            else:
                if msg[0] == OT.OUTPUT:
                    results.write(Text.from_markup(msg[1]))
                elif msg[0] == OT.PROMPT:
                    results.write(Text.from_markup(
                        f"[b magenta]{msg[1]}[/b magenta]"))
                elif msg[0] == OT.NOTIFY:
                    results.write(Text.from_markup(
                        f"[b yellow]{msg[1]}[/b yellow]"))
                elif msg[0] == OT.ERROR:
                    results.write(Text.from_markup(
                        f"[b red]{msg[1]}[/b red]"))
                elif msg[0] == OT.DEVICES:
                    self.__print_devices(results, msg[1])
                elif msg[0] == OT.CAN_MSG:
                    self.__print_can_msg(msg[1])
                elif msg[0] == OT.SIM_MSG:
                    simlogs.update(
                        Text.from_markup(self.__print_sim_msg(msg[1])))
                elif msg[0] == OT.TOTAL_STATS:
                    totalStats.update(
                        Text.from_markup(self.__print_total_stats(msg[1])))
                elif (msg[0] == OT.START_SESSION) or (msg[0] == OT.STOP_SESSION):
                    result = self.query_one(Results)
                    liveView = self.query_one(LiveView)
                    if result.has_class("-in-session"):
                        result.remove_class("-in-session")
                    else:
                        results.add_class("-in-session")
                    if liveView.has_class("-hidden"):
                        liveView.remove_class("-hidden")
                    else:
                        liveView.add_class("-hidden")
                elif msg[0] == OT.EXIT:
                    await asyncio.sleep(5)
                    self.exit()
                elif msg[0] == OT.BUFFERED_CAN_SIM:
                    self.__print_buffered_can_sim(simlogs, msg[1])
                else:
                    results.write(Text.from_markup(msg))

    def __print_buffered_can_sim(self, simlogs: Static, buffer: list) -> None:
        for msg in buffer:
            if msg[0] == OT.SIM_MSG:
                simlogs.update(Text.from_markup(self.__print_sim_msg(msg[1])))
            elif msg[0] == OT.CAN_MSG:
                self.__print_can_msg(msg[1])

    def __print_total_stats(self, msg) -> str:
        return (f"[b white]Simulator Messages:[/]\tSent: [green]{msg[0]}[/]\t\t"
                f"Dropped: [red]{msg[1]}[/]\tRetransmissions: [yellow]{msg[2]}[/]\n"
                f"[b white]CAN Messages:[/]\t\tSent: [green]{msg[3]}[/]\t\t"
                f"Dropped: [red]{msg[4]}[/]")

    def __print_sim_msg(self, msg) -> str:
        return (f"[b white]Throttle:[/] {msg[1]:0<4.4}\t"
                f"[b white]Steering:[/] {msg[2]:0<4.4}\t"
                f"[b white]Brake:[/] {int(msg[3])}\t"
                f"[b white]Hand Brake:[/] {msg[4]}\t"
                f"[b white]Reverse:[/] {msg[5]}\t"
                f"[b white]Gear:[/] {msg[7]}")

    def __print_can_msg(self, msg):
        if msg[1] in self.can_table._data.keys():
            if msg[2] != self.can_table._data[msg[1]][self._keys[1]]: # if length doesn't match
                self.can_table.update_cell(msg[1], self._keys[1], msg[2])
            if msg[3] != self.can_table._data[msg[1]][self._keys[2]]: # if data doesn't match
                self.can_table.update_cell(msg[1], self._keys[2], msg[3])
        else:
            self.can_table.add_row(*msg[1:], key=msg[1])

    def __print_devices(self, results: TextLog, devices: list) -> None:
        results.write(Rule("[green]Network Designer[/green]"))
        if len(devices) == 0:
            results.write(Text.from_markup(
                "[b red]Unfortunately, there are no available ECUs "
                "right now. Please check back later. [/b red]"))
        else:
            avail_ecus = Table(title="Available ECUs")
            avail_ecus.add_column(
                "ID", header_style="bright_yellow", style="yellow", no_wrap=True)
            avail_ecus.add_column(
                "Type", header_style="bright_cyan", style="cyan", no_wrap=True)
            avail_ecus.add_column("Make")
            avail_ecus.add_column("Model")
            avail_ecus.add_column("S/N")
            avail_ecus.add_column("Year")
            for device in devices:
                avail_ecus.add_row(
                    str(device["ID"]),
                    device["Devices"][0]["Type"][1],
                    device["Devices"][0]["Make"],
                    device["Devices"][0]["Model"],
                    device["Devices"][0]["SN"],
                    str(device["Devices"][0]["Year"])
                )
            results.write(avail_ecus)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Results()
        yield LiveView(classes="-hidden")
        yield CommandLine()
        yield TextLog(id="logViewer", classes="-hidden", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts."""
        # Give the input focus, so we can start typing straight away
        self.query_one(Input).focus()
        self.can_table = self.query_one(DataTable)
        self._keys = self.can_table.add_columns("ID", "Length", "Data")
        asyncio.create_task(self.monitor_output_queue())
        asyncio.create_task(self.monitor_log_queue())


    # def on_input_changed(self, command: Input.Changed) -> None:
    #     """Called when the user types something."""
    #     results = self.query_one(Results)
    #     liveView = self.query_one(LiveView)
    #     if results.has_class("-in-session"):
    #         results.remove_class("-in-session")
    #     else:
    #         results.add_class("-in-session")
    #     if liveView.has_class("-hidden"):
    #         liveView.remove_class("-hidden")
    #     else:
    #         liveView.add_class("-hidden")

    def on_input_submitted(self, command: Input.Submitted) -> None:
        """Called when the user presses enter."""
        self.cmd_conn.send(command.value)
        command.input.value = ""

    def exit(self) -> None:
        """Exit the app."""
        self._tui_stop.set()
        self.output_queue.put_nowait(None)
        self.log_output_queue.put_nowait(None)
        self.cmd_conn.send(None)
        super().exit("Bye!")


# if __name__ == "__main__":
#     output_queue = mp.Queue()
#     log_queue = mp.Queue()
#     cmd_conn, tui_conn = mp.Pipe()
#     tui = CANLayTUI(output_queue, log_queue, tui_conn)
#     tui.run()