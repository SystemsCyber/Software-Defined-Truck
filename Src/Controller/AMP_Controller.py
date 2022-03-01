#!/usr/bin/env python

from __future__ import print_function

import glob
import os

os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'
import sys

try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import argparse
import logging
import multiprocessing as mp
import random
import signal
import socket
from logging.handlers import QueueHandler
from multiprocessing.connection import Connection, Listener
from typing import Tuple

import carla
import pygame

import Text
from Controller import Controller
from Environment import LogListener
from NetworkMatrix import NetworkMatrix
from HUD import HUD
from KeyboardControl import KeyboardControl
from World import World

run = True


def handler_stop_signals(signum, frame):
    global run
    run = False


signal.signal(signal.SIGINT, handler_stop_signals)
signal.signal(signal.SIGTERM, handler_stop_signals)


def init_argparser() -> argparse.ArgumentParser:
    argparser = argparse.ArgumentParser(
        description='DARPA AMP Controller')

    arg_carla = argparser.add_argument_group("CARLA")
    arg_carla.add_argument(
        '-c', '--carla',
        metavar='ADDRESS',
        default='127.0.0.1',
        help='IP of the carla server (Default: 127.0.0.1)')
    arg_carla.add_argument(
        '-p', '--port',
        metavar='PORT',
        default=2000,
        type=int,
        help=(
            'TCP port to listen to the '
            'carla server on (Default: 2000)'
        ))
    arg_carla.add_argument(
        '-a', '--autopilot',
        action='store_true',
        help='Enable autopilot')
    arg_carla.add_argument(
        '--res',
        metavar='WIDTHxHEIGHT',
        default='1280x720',
        help='Game window resolution (Default: 1280x720)')
    arg_carla.add_argument(
        '--filter',
        metavar='PATTERN',
        default='vehicle.*',
        help='Actor filter (Default: "vehicle.*")')
    arg_carla.add_argument(
        '--rolename',
        metavar='NAME',
        default='hero',
        help='Actor role name (Default: "hero")')
    arg_carla.add_argument(
        '--gamma',
        default=2.2,
        type=float,
        help='Gamma correction of the camera (Default: 2.2)')

    arg_controller = argparser.add_argument_group("CONTROLLER")
    arg_controller.add_argument(
        '-s', '--server',
        metavar='ADDRESS',
        default='127.0.0.1',
        help=(
            'Address of the server to set up communication '
            'between the controller and SSSF (Default: 127.0.0.1)'
        ))
    arg_controller.add_argument(
        '-r', '--retransmissions',
        metavar='RETRANS',
        dest='retrans',
        default='2',
        type=int,
        choices=range(0, 4),
        help=(
            'Number of attempts to retransit lost controller/SSSF messages. '
            'The number of retransmissions determines the interval that '
            'the program checks for lost messages. If retransmissions '
            'is too high then messages will be considered lost before '
            'they\'ve had a chance to make it to other devices. As such '
            'this parameter is restricted to the range 0-3. '
            '(0 = OFF, Default: 2)'
        ))
    arg_controller.add_argument(
        '--pgn',
        metavar='PGN',
        nargs="+",
        help=(
            'A space separated list of important PGNs. Messages containing '
            'important PGNs require a response so the sender knows they have '
            'been received by at least one other device in the group. '
            'IMPORTANT: mark as few PGNs as important as possible. Marking '
            'all PGNs as important would effectively double the network load.'
        ))

    arg_network_matrix = argparser.add_argument_group("Network Matrix")
    arg_network_matrix.add_argument(
        '--display_mode',
        metavar='MODE',
        default='grouped',
        dest='display_mode',
        type=str,
        choices=["individual", "vertical", "horizontal", "grouped"],
        help=(
            'The display mode of the network matrix. Individual allows the user'
            'to pick which metric they would like to look at. Vertical and'
            'horizontal stack then next to each other in their respective'
            'directions. Grouped creates a matrix of the matrices.'
        ))
    arg_network_matrix.add_argument(
        '--display_totals',
        default=False,
        action='store_true',
        dest='display_totals',
        help=(
            'Displays the total number of packets sent and lost in the session'
            ' so far. (Default: OFF)'
        ))

    argparser.add_argument(
        '-v', '--verbose',
        action='store_true',
        dest='debug',
        default=False,
        help=(
            'Displays information about the running program. (Default: OFF)'
        ))
    return argparser


def init_mp_logging(queue: mp.Queue, log_level=logging.DEBUG):
    root = logging.getLogger()
    root.addHandler(QueueHandler(queue))
    root.setLevel(log_level)


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


def setup_loop(listener: Listener) -> Connection:
    conn = listener.accept()
    while True:
        msg = conn.recv()
        if (msg is None) or (msg == "break"):
            break
        elif msg == "ask":
            conn.send(input(''))
    return conn


def game_loop(conn: Connection, frame_rate: int, args):
    pygame.init()
    pygame.font.init()
    world = None

    try:
        client = carla.Client(args.carla, args.port)
        client.set_timeout(2.0)

        display = pygame.display.set_mode(
            (args.width, args.height),
            pygame.HWSURFACE | pygame.DOUBLEBUF)
        display.fill((0, 0, 0))
        pygame.display.flip()

        hud = HUD(args.width, args.height)
        world = World(client.get_world(), hud, args)
        # world = World(client.load_world('Town02'), hud, args)
        controller = KeyboardControl(world, args.autopilot)

        clock = pygame.time.Clock()
        while run:
            clock.tick_busy_loop(frame_rate)
            c = world.player.get_control()
            # p = world.player.get_physics_control()
            # t = world.player.get_transform()
            # v = world.player.get_velocity()
            conn.send((
                float(c.throttle),
                float(c.steer),
                float(c.brake),
                float(c.hand_brake),
                float(c.reverse),
                float(c.manual_gear_shift),
                float(c.gear)
            ))
            if controller.parse_events(client, world, clock):
                return
            world.tick(clock)
            world.render(display)
            pygame.display.flip()

    finally:

        if (world and world.recording_enabled):
            client.stop_recorder()

        if world is not None:
            world.destroy()
        pygame.quit()


def main():
    argparser = init_argparser()
    args = argparser.parse_args()
    args.width, args.height = [int(x) for x in args.res.split('x')]
    log_level = logging.DEBUG if args.debug else logging.INFO
    frame_rate = 60

    health_queue = mp.Queue()
    log_queue = mp.Queue()
    listen_for_logs = mp.Event()
    listen_for_logs.set()

    log_listener = mp.Process(
        target=LogListener.listen, args=(listen_for_logs, log_queue))
    log_listener.start()

    init_mp_logging(log_queue, log_level)
    # mp_logger = mp.get_logger()
    # mp_logger.propagate = True
    # mp_logger.setLevel(log_level)
    Text.printdoc()
    logging.info('Listening to carla server %s:%s.', args.carla, args.port)

    ctrl = Controller(
        _retrans=args.retrans,
        _frame_rate=frame_rate,
        _server_ip=args.server
    )
    matrix = NetworkMatrix()
    port = choose_ipc_port()
    running = mp.Event()
    running.set()
    matrix_thread = mp.Process(
        target=matrix.animate,
        args=(health_queue, args.display_mode, args.display_totals),
        daemon=True
        )
    ctrl_thread = mp.Process(
        target=ctrl.start, args=(port, running, log_queue, health_queue, log_level))
    listener = Listener(('localhost', port), authkey=ctrl_thread.authkey)

    ctrl_thread.start()
    matrix_thread.start()
    conn = setup_loop(listener)
    game_loop(conn, frame_rate, args)

    running.clear()
    listener.close()
    health_queue.close()
    health_queue.join_thread()
    ctrl_thread.join(2)
    matrix_thread.join(1)
    ctrl_thread.terminate()
    ctrl_thread.close()
    
    listen_for_logs.clear()
    log_listener.join(2)
    log_listener.close()


if __name__ == '__main__':

    main()
