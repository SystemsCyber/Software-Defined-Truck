#!/usr/bin/env python

"""
Welcome to CARLA manual control.

Use ARROWS or WASD keys for control.

    W            : throttle
    S            : brake
    A/D          : steer left/right
    Q            : toggle reverse
    Space        : hand-brake
    P            : toggle autopilot
    M            : toggle manual transmission
    ,/.          : gear up/down
    CTRL + W     : toggle constant velocity mode at 60 km/h

    L            : toggle next light type
    SHIFT + L    : toggle high beam
    Z/X          : toggle right/left blinker
    I            : toggle interior light

    TAB          : change sensor position
    ` or N       : next sensor
    [1-9]        : change to sensor [1-9]
    G            : toggle radar visualization
    C            : change weather (Shift+C reverse)
    Backspace    : change vehicle

    V            : Select next map layer (Shift+V reverse)
    B            : Load current selected map layer (Shift+B to unload)

    R            : toggle recording images to disk

    CTRL + R     : toggle recording of simulation (replacing any previous)
    CTRL + P     : start replaying last recorded simulation
    CTRL + +     : increments the start time of the replay by 1 second (+SHIFT = 10 seconds)
    CTRL + -     : decrements the start time of the replay by 1 second (+SHIFT = 10 seconds)

    F1           : toggle HUD
    H/?          : toggle help
    ESC          : quit
"""

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

import carla
import signal
import multiprocessing as mp
import argparse
import logging
import pygame
from HUD import HUD
from World import World
from KeyboardControl import KeyboardControl
from Controller import Controller
from CANNode import ColoredConsoleHandler
from logging.handlers import TimedRotatingFileHandler

run = True

def handler_stop_signals(signum, frame):
    global run
    run = False

signal.signal(signal.SIGINT, handler_stop_signals)
signal.signal(signal.SIGTERM, handler_stop_signals)

def game_loop(parent_conn, args):
    pygame.init()
    pygame.font.init()
    world = None

    try:
        client = carla.Client(args.host, args.port)
        client.set_timeout(2.0)

        display = pygame.display.set_mode(
            (args.width, args.height),
            pygame.HWSURFACE | pygame.DOUBLEBUF)
        display.fill((0,0,0))
        pygame.display.flip()

        hud = HUD(args.width, args.height)
        world = World(client.get_world(), hud, args)
        # world = World(client.load_world('Town02'), hud, args)
        controller = KeyboardControl(world, args.autopilot)

        clock = pygame.time.Clock()
        while run:
            clock.tick_busy_loop(60)
            c = world.player.get_control()
            # p = world.player.get_physics_control()
            # t = world.player.get_transform()
            # v = world.player.get_velocity()
            parent_conn.send((
                c.throttle,
                c.steer,
                c.brake,
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

def findpath(log_name):
        base_dir = os.path.abspath(os.getcwd())
        for root, dirs, files in os.walk(base_dir):
            for name in dirs:
                if name == "Logs":
                    log_path = os.path.join(root, name)
                    return os.path.join(log_path, log_name)
        log_path = os.path.join(base_dir, "Logs")
        return os.path.join(log_path, log_name)
    
def init_logging() -> None:
    filename = findpath("controller_log")
    logging.basicConfig(
        format='%(asctime)-15s %(module)-10.10s %(levelname)s %(message)s',
        level=logging.DEBUG,
        handlers=[
            TimedRotatingFileHandler(
                filename=filename,
                when="midnight",
                interval=1,
                backupCount=7,
                encoding='utf-8'
                ),
            ColoredConsoleHandler()
            ]
        )

def main():
    argparser = argparse.ArgumentParser(
        description='DARPA AMP Control Client')
    argparser.add_argument(
        '-v', '--verbose',
        action='store_true',
        dest='debug',
        help='print debug information')
    argparser.add_argument(
        '--host',
        metavar='H',
        default='127.0.0.1',
        help='IP of the host server (default: 127.0.0.1)')
    argparser.add_argument(
        '--server_host',
        metavar='S',
        default='127.0.0.1',
        help='IP of the server to set up communication between the controller and SSSF (default: 127.0.0.1)')
    argparser.add_argument(
        '-p', '--port',
        metavar='P',
        default=2000,
        type=int,
        help='TCP port to listen to (default: 2000)')
    argparser.add_argument(
        '-a', '--autopilot',
        action='store_true',
        help='enable autopilot')
    argparser.add_argument(
        '--res',
        metavar='WIDTHxHEIGHT',
        default='1280x720', # originally 1280 x 720
        help='window resolution (default: 1280x720)')
    argparser.add_argument(
        '--filter',
        metavar='PATTERN',
        default='vehicle.*',
        help='actor filter (default: "vehicle.*")')
    argparser.add_argument(
        '--rolename',
        metavar='NAME',
        default='hero',
        help='actor role name (default: "hero")')
    argparser.add_argument(
        '--gamma',
        default=2.2,
        type=float,
        help='Gamma correction of the camera (default: 2.2)')
    args = argparser.parse_args()
    args.width, args.height = [int(x) for x in args.res.split('x')]

    log_level = logging.DEBUG if args.debug else logging.INFO
    init_logging()
    logging.info('listening to server %s:%s', args.host, args.port)
    print(__doc__)

    ctrl = Controller()
    parent_conn, child_conn = mp.Pipe()
    listen = mp.Event()
    listen.set()
    ctrl_thread = mp.Process(target=ctrl.start, args=(child_conn, listen,))

    ctrl_thread.start()
    game_loop(parent_conn, args)
    listen.clear()
    ctrl_thread.join(3)
    ctrl_thread.close()

if __name__ == '__main__':

    main()
