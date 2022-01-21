#!/usr/bin/env python

from __future__ import print_function

import glob
import os
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
from multiprocessing import SimpleQueue
import signal

import carla
import pygame

import Text
from Controller import Controller
from Environment import LogSetup
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

    argparser.add_argument(
        '-v', '--verbose',
        action='store_true',
        dest='debug',
        default=False,
        help=(
            'Displays information about the running program. (Default: OFF)'
        ))
    return argparser


def setup_loop(conn: SimpleQueue) -> None:
    while True:
        msg = conn.get()
        if (msg is None) or (msg == "break"):
            break
        elif msg == "ask":
            conn.put(input(''))


def game_loop(conn: SimpleQueue, frame_rate: int, args):
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
            if not conn.empty():
                conn.get()
            conn.put((
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

    LogSetup.init_logging(log_level)
    Text.printdoc()
    logging.info('Listening to carla server %s:%s.', args.carla, args.port)

    ctrl = Controller(
        _retrans=args.retrans,
        _frame_rate=frame_rate,
        _server_ip=args.server
    )
    conn = mp.SimpleQueue()
    listen = mp.Event()
    listen.set()
    ctrl_thread = mp.Process(target=ctrl.start, args=(conn, listen,))

    ctrl_thread.start()
    setup_loop(conn)
    game_loop(conn, frame_rate, args)
    listen.clear()
    ctrl_thread.join(3)
    ctrl_thread.close()


if __name__ == '__main__':

    main()
