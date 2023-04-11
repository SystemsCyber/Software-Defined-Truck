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
from multiprocessing.connection import Client
from multiprocessing.connection import Connection

import carla
import pygame

from HUD import HUD
from KeyboardControl import KeyboardControl
from World import World


def init_argparser() -> argparse.ArgumentParser:
    argparser = argparse.ArgumentParser(
        description='Carla Controller')

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
    argparser.add_argument(
        '-v', '--verbose',
        action='store_true',
        dest='debug',
        default=False,
        help=(
            'Displays information about the running program. (Default: OFF)'
        ))
    arg_canlay = argparser.add_argument_group("CANLay")
    arg_canlay.add_argument(
        '--ipc_port',
        metavar='PORT',
        default=3000,
        type=int,
        help=("TCP port to listen to the CANLay server on. (Default: 3000)"))
    arg_canlay.add_argument(
        '--ipc_pass',
        metavar='PASSWORD',
        type=int,
        help=("Password to authenticate IPC messages from CANLay server."))
    return argparser


def game_loop(frame_rate: int, args):
    pygame.init()
    pygame.font.init()
    world = None
    canlay_conn = Client(('localhost', args.ipc_port),
                        authkey=args.ipc_pass.to_bytes(32, 'big'))

    try:
        client = carla.Client(args.carla, args.port)
        client.set_timeout(10.0)

        display = pygame.display.set_mode((args.width, args.height),
            pygame.HWSURFACE | pygame.DOUBLEBUF)
        display.fill((0, 0, 0))
        pygame.display.flip()

        hud = HUD(args.width, args.height)
        # world = World(client.get_world(), hud, args)
        world_map = client.load_world('Town02_Opt')
        world = World(world_map, hud, args)
        world_map.unload_map_layer(carla.MapLayer.Buildings)
        world_map.unload_map_layer(carla.MapLayer.Decals)
        world_map.unload_map_layer(carla.MapLayer.Foliage)
        world_map.unload_map_layer(carla.MapLayer.Ground)
        world_map.unload_map_layer(carla.MapLayer.ParkedVehicles)
        world_map.unload_map_layer(carla.MapLayer.Particles)
        world_map.unload_map_layer(carla.MapLayer.Props)
        world_map.unload_map_layer(carla.MapLayer.StreetLights)
        world_map.unload_map_layer(carla.MapLayer.Walls)
        controller = KeyboardControl(world, args.autopilot)
        

        clock = pygame.time.Clock()
        while True:
            clock.tick_busy_loop(frame_rate)
            c = world.player.get_control()
            # p = world.player.get_physics_control()
            # t = world.player.get_transform()
            # v = world.player.get_velocity()

            # These network functions take time and could block, but we need to
            # incorporate them into the game loop without asyncio so that they
            # are incorporated into the simulation asap.
            try:
                if canlay_conn.poll():
                    data = canlay_conn.recv()
                    if data is None:
                        break
                canlay_conn.send((
                    float(c.throttle),
                    float(c.steer),
                    float(c.brake),
                    float(c.hand_brake),
                    float(c.reverse),
                    float(c.manual_gear_shift),
                    float(c.gear)
                ))
            except (EOFError, ConnectionResetError):
                break
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
    logging.basicConfig(format='%(levelname)s: %(message)s', level=log_level)

    logging.info('listening to server %s:%s', args.carla, args.port)

    print(__doc__)
    frame_rate = 60

    try:
        game_loop(frame_rate, args)
    except KeyboardInterrupt:
        print('\nCancelled by user. Bye!')



if __name__ == '__main__':

    main()
