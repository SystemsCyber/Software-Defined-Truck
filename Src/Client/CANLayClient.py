#!/usr/bin/env python
from __future__ import annotations

import asyncio
import ipaddress
import logging
import multiprocessing as mp
import os
import random
import socket
import sys
import threading as th
from enum import Enum
from multiprocessing.connection import Listener
from pathlib import Path

import typer
from Controller import Controller
from TUI import CANLayTUI

sys.path.insert(0, str(Path('../').resolve()))
from CANLay.Environment import CANLayLogger, OutputType


# This came from an example. Needed to have it for Windows with asyncio.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = typer.Typer()


def choose_ipc_port() -> int:
    ports = [random.randrange(2**12, 2**16) for i in range(10)]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        for port in ports:
            logging.debug("Choosing a port for IPC.")
            result = sock.connect_ex(('localhost', port))
            if result == 0:
                logging.error(f"Port {port} is in use. Choosing another.")
            else:
                return port
        logging.error("Cannot find a free port. Exiting...")
        exit()


def get_listening_port() -> int:
    try:
        sim_port = choose_ipc_port()
        _ = Listener(
            ('localhost', sim_port), authkey=mp.current_process().authkey)
        return sim_port
    except OSError as e:
        logging.error(f"Error while choosing a port: {e}")
        logging.debug("Trying again...")
        return get_listening_port()


async def read_sim_logs(stream, cb):
    while True:
        if stream is None:
            break
        line = await stream.readline()
        if not line:
            break
        cb((OutputType.OUTPUT, line.decode("utf-8").rstrip()))


async def carla(
    sim_stop_event: asyncio.Event, host: str, port: int,
    autopilot: bool, resolution: str, filter: str, role_name: str,
    gamma: float, ipc_port: int, output
):
    ipc_pass = str(int.from_bytes(mp.current_process().authkey, "big"))
    carla_args = [
        "--carla", host, "--port", str(port), "--res", resolution,
        "--filter", filter, "--rolename", role_name, "--gamma", str(gamma),
        "--ipc_port", str(ipc_port), "--ipc_pass", ipc_pass
    ]
    if autopilot:
        carla_args.append("--autopilot")
    carla_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "Carla-Client")
    carla_proc = await asyncio.create_subprocess_exec(
        *["python", "CarlaController.py", *carla_args],
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        cwd=carla_path)
    await asyncio.wait([
        read_sim_logs(carla_proc.stdout, output),
        read_sim_logs(carla_proc.stderr, output)
    ])
    # Hasn't worked
    # if await sim_stop_event.wait():
    #     carla_proc.kill()
    return await carla_proc.wait()


async def run_simulator(
    sim_stop_event: asyncio.Event, simulator: Simulator, host: str,
    port: int, autopilot: bool, resolution: str, filter: str, role_name: str,
    gamma: float, ipc_port: int, output
):
    if simulator == Simulator.CARLA:
        return await carla(sim_stop_event, host, port, autopilot, resolution,
                           filter, role_name, gamma, ipc_port, output)
    if simulator == Simulator.NONE:
        return 0
    else:
        logging.error("Invalid simulator.")
        return 1


def check_server(host: str):
    """Checks that the host is a valid IP address or fully qualified domain name
    and throws typer.BadParameter if not."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            socket.gethostbyname(host)
        except socket.gaierror:
            raise typer.BadParameter(f"Invalid host: {host}")
    return host


class DisplayMode(str, Enum):
    INDIVIDUAL = "individual"
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    GROUPED = "grouped"


class Simulator(str, Enum):
    NONE = "none"
    CARLA = "carla"


def main(
    broker: str = typer.Argument(
        "127.0.0.1", help="IP address of the CANLay broker.",
        callback=check_server),
    port: int = typer.Argument(
        80,
        help="Port of the CANLay broker.",
        min=0, max=65535, show_default=True),
    simulator: Simulator = typer.Option(
        Simulator.NONE, "--simulator", "-s",
        help="Simulator to use such as CARLA or None.",
        case_sensitive=False, show_default=True, show_choices=True),
    retransmissions: int = typer.Option(
        1, "--retransmissions", "-r",
        help=(
        'Number of attempts to retransit lost controller/SSSF messages. '
        'The number of retransmissions determines the interval that '
        'the program checks for lost messages. If retransmissions '
        'is too high then messages will be considered lost before '
        'they\'ve had a chance to make it to other devices. As such '
        'this parameter is restricted to the range 0-3. '
        '(0 = OFF, Default: 2)'),
        min=0, max=3, show_default=True, clamp=True),
    pgn: str = typer.Option(
        None, "--pgn",
        help=(
            'A space separated list of important PGNs. Messages containing '
            'important PGNs require a response so the sender knows they have '
            'been received by at least one other device in the group. '
            'IMPORTANT: mark as few PGNs as important as possible. Marking '
            'all PGNs as important would effectively double the network load.'),
        min=0, max=0xFFFFFF),
    filename: str = typer.Option(
        "", "--filename", "-f",
        help="The name of the file to save the can and simulator logs to."),
    verbose: int = typer.Option(
        0, "--verbose", "-v",
        help="Enable verbose output. More v's increases verbosity.",
        min=0, max=3, show_default=True, clamp=True, count=True),
    display_mode: DisplayMode = typer.Option(
        DisplayMode.GROUPED,
        help=(
            'The display mode of the network matrix. Individual allows the user'
            'to pick which metric they would like to look at. Vertical and'
            'horizontal stack then next to each other in their respective'
            'directions. Grouped creates a matrix of the matrices.'),
        show_default=True, case_sensitive=False, show_choices=True,
        rich_help_panel="Network Display Options"),
    display_totals: bool = typer.Option(
        False,
        help=(
            'Displays the total number of packets sent and lost in the session'
            ' so far. (Default: OFF)'),
        show_default=True,
        rich_help_panel="Network Display Options"),
    carla_host: str = typer.Option(
        "127.0.0.1", "--carla_host",
        help="IP address of the CARLA simulator.",
        callback=check_server, show_default=True, rich_help_panel="CARLA Simulator Options"),
    carla_port: int = typer.Option(
        2000, "--carla_port",
        help="Port of the CARLA simulator.",
        min=0, max=65535, show_default=True, rich_help_panel="CARLA Simulator Options"),
    carla_autopilot: bool = typer.Option(
        False, "--carla_autopilot",
        help="Enable autopilot in the CARLA simulator.",
        show_default=True, rich_help_panel="CARLA Simulator Options"),
    carla_resolution: str = typer.Option(
        "1280x720", "--carla_resolution",
        help="Resolution of the CARLA simulator.",
        show_default=True, rich_help_panel="CARLA Simulator Options"),
    carla_filter: str = typer.Option(
        "vehicle.*", "--carla_filter",
        help="Filter of the CARLA simulator.",
        rich_help_panel="CARLA Simulator Options"),
    carla_role_name: str = typer.Option(
        "hero", "--carla_role_name",
        help="Role name of the CARLA simulator.",
        rich_help_panel="CARLA Simulator Options"),
    carla_gamma: float = typer.Option(
        2.2, "--carla_gamma",
        help="Gamma of the CARLA simulator.",
        rich_help_panel="CARLA Simulator Options"),
):
    """
    CANLay - A powerful application for testing Electronic Control Units (ECUs)

    Overview: 
    CANLay is a tool that streamlines the testing process for ECUs. It overlays a CAN network onto the TCP/IP layer, creating a distributed hardware-in-the-loop testing environment. With CANLay, you can improve your testing process and take control of your ECU development.
    """
    # Set log level based on verbose flag
    log_level = logging.ERROR
    if verbose == 1:
        log_level = logging.WARNING
    elif verbose == 2:
        log_level = logging.INFO
    elif verbose == 3:
        log_level = logging.DEBUG
    loop = asyncio.get_event_loop()
    mp.set_start_method('spawn')
    output = mp.Queue()
    # Set up logging
    # Central Log Queue for all processes
    log_queue = mp.Queue()
    log_output_queue = mp.Queue()
    # Configure Main Process Logging
    CANLayLogger.worker_configure(log_queue, log_level)
    # Setup TUI
    # Connection between the TUI and the Controller
    tui_conn, ctrl_conn = mp.Pipe()
    # TUI
    tui = CANLayTUI(output, log_output_queue, tui_conn)
    # Setup Simulator
    # Connection between the simulator and the Controller
    sim_port = get_listening_port()

    sim = False
    if simulator != Simulator.NONE:
        sim = True

    record = False
    if len(filename) > 0:
        record = True
    # Setup Controller
    ctrl = Controller()
    ctrl_thread = mp.Process(
        target=ctrl.run,
        args=(broker, port, retransmissions, record, filename, 
              log_level, ctrl_conn, output, log_queue, log_output_queue,
              sim, sim_port, mp.current_process().authkey),)

    tui_task = loop.create_task(tui.run_async())
    sim_stop_event = asyncio.Event()
    sim_proc = loop.create_task(run_simulator(
        simulator=simulator,
        sim_stop_event=sim_stop_event,
        host=carla_host,
        port=carla_port,
        autopilot=carla_autopilot,
        resolution=carla_resolution,
        filter=carla_filter,
        role_name=carla_role_name,
        gamma=carla_gamma,
        ipc_port=sim_port,
        output=output.put_nowait
    ))
    try:
        ctrl_thread.start()
        loop.run_until_complete(asyncio.gather(tui_task, sim_proc))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(e)
    finally:
        logging.info("Shutting down...")
        # Tell the controller to shut down
        tui_conn.close()
        ctrl_conn.close()
        # Wait for the Controller to finish shutting down Close the Controller
        # and hopefully it will close the Simulator
        ctrl_thread.join(6)
        ctrl_thread.terminate()
        ctrl_thread.close()
        # Stop waiting for simulator output
        sim_stop_event.set()
        if sim_proc:
            sim_proc.cancel()  # type: ignore


if __name__ == '__main__':
    typer.run(main)
