import re
import multiprocessing as mp
from multiprocessing.connection import PipeConnection
from typing import List
import logging
import ctypes as ct
import sys
import logging
from pathlib import Path
# ==============================================================================
sys.path.insert(0, str(Path('../').resolve()))
from CANLay.CANNode import CAN_message
from CANLay.Environment import CANLayLogger
from CANLay.Environment import OutputType as OT
from CANLay import LOGTYPE_FILE, LOGTYPE_OUTPUT
from CANLay import CANLay
# ==============================================================================


class Controller:
    def __init__(self) -> None:
        self._cansend_re = re.compile(
            r'^(?P<id>[0-9A-Fa-f]{3,8})(?:#|(?P<flags>#[RF]\d?|[\da-fA-F]{0,15}##[0-9A-Fa-f])?)(?P<data>(?:\.?[0-9A-Fa-f]{0,2}){0,8})$')

    def run(self,
              broker_host,
              broker_port,
              retransmissions,
              record,
              record_filename,
              log_level,
              command_pipe: PipeConnection,
              output: mp.Queue,
              log_queue: mp.Queue,
              log_output_queue: mp.Queue,
              simulator: bool = False,
              simulator_port: int = 0,
              auth_key: bytes = b''):
        CANLayLogger.worker_configure(log_queue, log_level)
        self.__command = command_pipe
        self.output = output
        self.canlay = CANLay(
            broker_host=broker_host,
            broker_port=broker_port,
            retransmissions=retransmissions,
            record=record,
            record_filename=record_filename,
            log_level=log_level,
            log_type=(LOGTYPE_FILE | LOGTYPE_OUTPUT),
            log_filename="CANLay.log",
            log_directory_path="Logs"
        )
        self.canlay.start(
            simulator=simulator,
            sim_port=simulator_port,
            auth_key=auth_key,
            output_queue=output,
            log_queue=log_queue,
            log_output_queue=log_output_queue
        )
        if self.provision_devices():
            self.canlay.start_session()
            self.monitor_commands()
        self.canlay.stop()

    def __print_devices(self, available_devices: list) -> List[int]:
        # Discard any commands that have been sent to the controller
        try:
            if (self.__command.poll()):
                self.__command.recv()
            self.output.put((OT.DEVICES, available_devices))
            self.output.put((OT.PROMPT,
                             "Enter the numbers corresponding to the ECUs you "
                             "would like to use (comma separated): "))
            answer = self.__command.recv()  # Wait for user input
            input_list = str(answer).split(',')
            return [int(i.strip()) for i in input_list]
        except (EOFError, BrokenPipeError, ValueError):
            self.canlay.stop_session()
            return []

    def __request_user_input(self, available: list) -> List[int]:
        available_device_ids = [device["ID"] for device in available]
        requested = self.__print_devices(available)
        if requested == []:
            return []
        if set(requested).issubset(available_device_ids):
            if self.canlay.request_devices(requested, available):
                self.output.put(
                    (OT.NOTIFY, "Devices successfully allocated."))
                return requested
            else:
                self.output.put((OT.ERROR,
                                 "One or more of the requested devices are no longer "
                                 "available. Please select new device(s)."))
                return self.provision_devices()
        else:
            self.output.put((OT.ERROR,
                             "One or more numbers entered do not correspond"
                             " with the available devices. Please try again."))
            return self.__request_user_input(available)

    def provision_devices(self) -> List[int]:
        available_devices = self.canlay.get_devices()
        if len(available_devices) > 0:
            return self.__request_user_input(available_devices)
        else:
            self.output.put((OT.DEVICES, []))
            return []

    def monitor_commands(self) -> None:
        while not self.canlay.stop_event.is_set():
            if self.__command.poll(0.5):
                try:
                    command: str = self.__command.recv()
                except EOFError:
                    logging.debug("Command IPC socket closed.")
                    self.canlay.stop_session()
                else:
                    if command is not None:
                        self.__handle_commands(command.split())
                    else:
                        logging.debug("Command IPC socket closed.")
                        self.canlay.stop_session()

    def __handle_commands(self, command: List[str]) -> None:
        if command[0] == "cansend":
            c = self._cansend_re.match(command[1])
            if c is not None:
                params = c.groupdict()
                id = int(params["id"], 16)
                length = 0
                data = bytearray()
                if "flags" in params.keys() and params["flags"] is not None:
                    flags = params["flags"].strip("#")
                    if "R" in flags and len(flags) > 1:
                        length = int(flags[-1])
                        data = bytearray([0] * int(length))
                    elif "R" in flags:
                        length = 0
                        data = bytearray()
                    else:
                        self.output.put(
                            (OT.ERROR, "FD Not yet supported."))
                        return
                if "data" in params.keys() and params["data"] is not None:
                    if "." in params["data"]:
                        for d in params["data"].split("."):
                            data.append(int(d, 16))
                        length = len(data)
                    else:
                        data = bytearray.fromhex(params["data"])
                        length = len(data)
            else:
                self.output.put((OT.ERROR, "Invalid CAN frame."))
                return
            msg = CAN_message(ct.c_uint32(id), ct.c_uint8(length))
            for i in range(length):
                msg.buf[i] = ct.c_uint8(data[i])
            self.canlay.write_can(False, False, msg)
            return
