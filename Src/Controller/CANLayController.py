from __future__ import annotations

import threading as th
import logging
import selectors as sel
import ctypes as ct
from io import BytesIO
import multiprocessing as mp
from multiprocessing.connection import Client, Connection, Listener, PipeConnection
from time import time, sleep
from types import SimpleNamespace
from typing import List

from HealthReport import HealthReport
from TUI import TUIOutput as TO
from Environment import CANLayLogger
from CANNode import CAN_message
from Recorder import Recorder
from Recorder import RecordType as RT
import re
from NetworkManager import NetworkManager


class Controller(NetworkManager):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._display_mode = kwargs["_display_mode"]
        self._display_totals = kwargs["_display_totals"]
        self._cansend_re = re.compile(
            r'^(?P<id>[0-9A-Fa-f]{3,8})(?:#|(?P<flags>#[RF]\d?|[\da-fA-F]{0,15}##[0-9A-Fa-f])?)(?P<data>(?:\.?[0-9A-Fa-f]{0,2}){0,8})$')

    def __listen(self) -> None:
        while not self.close_connection and not self.stop_event.is_set():
            with self.sel_lock:
                connection_events = self.sel.select(
                    timeout=self.timeout_additive)
                for key, mask in connection_events:
                    callback = key.data.callback
                    callback(key)
            self.check_members(self.time_us() / 1000000)

    def __print_devices(self, available_devices: list) -> List[int]:
        # Discard any commands that have been sent to the controller
        try:
            if (self._command.poll()):
                self._command.recv()
            self.tui_output.put((TO.DEVICES, available_devices))
            self.tui_output.put((TO.PROMPT,
                                 "Enter the numbers corresponding to the ECUs you "
                                 "would like to use (comma separated): "))
            answer = self._command.recv()  # Wait for user input
            input_list = str(answer).split(',')
            return [int(i.strip()) for i in input_list]
        except (EOFError, BrokenPipeError, ValueError):
            self.stop_session()
            return []

    def __request_user_input(self, available: list) -> List[int]:
        available_device_ids = [device["ID"] for device in available]
        requested = self.__print_devices(available)
        if requested == []:
            return []
        if set(requested).issubset(available_device_ids):
            if self.request_devices(requested, available):
                self.tui_output.put(
                    (TO.NOTIFY, "Devices successfully allocated."))
                return requested
            else:
                self.tui_output.put((TO.ERROR,
                                     "One or more of the requested devices are no longer "
                                     "available. Please select new device(s)."))
                return self.__provision_devices()
        else:
            self.tui_output.put((TO.ERROR,
                                 "One or more numbers entered do not correspond"
                                 " with the available devices. Please try again."))
            return self.__request_user_input(available)

    def __provision_devices(self) -> List[int]:
        available_devices = self.get_devices()
        if len(available_devices) > 0:
            return self.__request_user_input(available_devices)
        else:
            self.tui_output.put((TO.DEVICES, []))
            return []

    def __accept_sim_conn(self, sim_sock: Listener) -> None:
        try:
            self._sim_conn = sim_sock.accept()
            with self.sel_lock:
                self.sel.register(self._sim_conn, sel.EVENT_READ,
                                  SimpleNamespace(callback=self.read_signals))
            logging.debug("Simulation connection accepted.")
        except OSError:
            logging.debug("Simulation socket closed.")

    def __monitor_commands(self) -> None:
        while not self.stop_event.is_set():
            if self._command.poll(0.5):
                try:
                    command: str = self._command.recv()
                except EOFError:
                    logging.debug("Command IPC socket closed.")
                    self.stop_session()
                else:
                    if command is not None:
                        self.__handle_commands(command.split())
                    else:
                        logging.debug("Command IPC socket closed.")
                        self.stop_session()

    def __handle_commands(self, command: list[str]) -> None:
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
                        self.tui_output.put(
                            (TO.ERROR, "FD Not yet supported."))
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
                self.tui_output.put((TO.ERROR, "Invalid CAN frame."))
                return
            msg = CAN_message(ct.c_uint32(id), ct.c_uint8(length))
            for i in range(length):
                msg.buf[i] = ct.c_uint8(data[i])
            self.can_key.data.callback = self.write_can
            self.can_key.data.message = (False, False, msg) # need_response, fd, msg
            with self.sel_lock:
                self.sel.modify(self.can_key.fileobj,
                                sel.EVENT_WRITE, self.can_key.data)
            return

    def __request_health_loop(self) -> None:
        try:
            while not self.stop_event.is_set():
                self.request_health()
                sleep(1)  # Wait 1 second before sending next health request
        except Exception as e:
            logging.debug(e, exc_info=True)

    def __send_sync_loop(self) -> None:
        try:
            init_count = 5
            init_count_remaining = init_count
            while not self.stop_event.is_set():
                if self.in_session.wait(1):
                    self.send_sync()
                    if init_count >= 0:
                        init_count_remaining -= 1
                        sleep(0.2)
                        continue
                    sleep(1)
        except Exception as e:
            logging.debug(e, exc_info=True)

    def start(
            self,
            sim_sock: Listener,
            command: PipeConnection,
            output: mp.Queue,
            record_filename: str,
            log_queue: mp.Queue,
            log_level: int
    ) -> None:
        CANLayLogger.worker_configure(log_queue, log_level)
        self.tui_output = output
        self.stop_event = th.Event()
        self.in_session = th.Event()
        self.recorder_output = mp.Queue()
        self._record_filename = record_filename
        self._command = command
        self._log_queue = log_queue
        self._log_level = log_level
        self._stop_mp = mp.Event()
        sim_thread = th.Thread(target=self.__accept_sim_conn, args=(sim_sock,))
        ptp_thread = th.Thread(target=self.__send_sync_loop)
        health_thread = th.Thread(target=self.__request_health_loop)
        command_thread = th.Thread(target=self.__monitor_commands)
        try:
            sim_thread.start()
            ptp_thread.start()
            health_thread.start()
            self.tui_output.put((TO.NOTIFY, "Connecting..."))
            if self.connect():
                self.tui_output.put((TO.NOTIFY, "Registering..."))
                if self.register():
                    if self.__provision_devices():
                        with self.sel_lock:
                            self.sel.modify(self.ctrl.sock, sel.EVENT_READ,
                                            SimpleNamespace(
                                                callback=self.receive_SSE,
                                                outgoing_message=None))
                            command_thread.start()
                        with BytesIO(self.response_data) as self.rfile:
                            self.do_POST()
                        self.__listen()
                else:
                    self.tui_output.put((TO.ERROR, "Failed to register."))
            else:
                self.tui_output.put((TO.ERROR, "Failed to connect."))
        except Exception as e:
            logging.error(e, exc_info=True)
        finally:
            # Tell the user we are exiting
            self.tui_output.put((TO.NOTIFY, "Exiting..."))
            # Tell the Network Matrix to stop
            self._stop_mp.set()
            # If we haven't set these events, do it now
            if not self.stop_event.is_set():
                self.stop_event.set()
            if self.in_session.is_set():
                self.in_session.clear()
            else:
                # The do_delete from the server should not close the application
                pass
            # Check if we setup the health report, if so stop it
            if hasattr(self, 'health_report'):
                self.health_report.stop_display()
            # Check if we setup the recording process, if so stop it
            if hasattr(self, "recorder"):
                self.recorder_output.put(None)
                self.recorder.join()
                self.recorder.close()
                while(not self.recorder_output.empty()):
                    self.recorder_output.get()
            self.recorder_output.close()
            # Check if we still have a connection with the simulator. If so,
            # close it.
            if hasattr(self, '_sim_conn'):
                # Tell it to stop by sending the none
                self._sim_conn.send(None)
                # Recv any messages that may be left so we don't get stuck open.
                while(self._sim_conn.poll()):
                    self._sim_conn.recv()
                # Close the socket
                self.sel.unregister(self._sim_conn)
                self._sim_conn.close()
            # Close the listen socket
            sim_sock.close()
            # Close the command pipe
            self._command.close()
            # If the threads are still running, wait for them to finish
            if sim_thread.is_alive():
                sim_thread.join()
            # if ntp_thread.is_alive():
            #     ntp_thread.join()
            if ptp_thread.is_alive():
                ptp_thread.join()
            if command_thread.is_alive():
                command_thread.join()
            if health_thread.is_alive():
                health_thread.join()
            # If somehow we got here and the TUI is still up, tell it to exit
            self.tui_output.put((TO.EXIT, ""))
            # Disconnect from the server
            self.stop()
            # Close remaining resources
            while(not self.tui_output.empty()):
                self.tui_output.get()
            self.tui_output.close()
            log_queue.close()

    def do_POST(self):  # Equivalent of start
        try:
            ip, port, request_data = super().do_POST()
            if ip:
                self.tui_output.put((TO.NOTIFY, "Session established."))
                logging.debug(request_data)
                self.start_session(ip, port, request_data)
                self.health_report = HealthReport(self.members)
                self.health_report.start_display(
                    self._stop_mp, self.tui_output, self._log_queue, self._log_level)
                if len(self._record_filename) > 0:
                    recorder = Recorder(self._record_filename)
                    self.recorder = mp.Process(
                        target=recorder.start_recording,
                        args=(self.recorder_output, self._stop_mp,
                              self._log_queue, self._log_level))
                    self.recorder.start()
                    self.recording = True
                self.in_session.set()
            else:
                self.tui_output.put(
                    (TO.ERROR, "Session could not be established."))
        except TypeError as te:
            logging.error(te)

    def do_DELETE(self):  # Equivalent of stop
        self.tui_output.put((TO.NOTIFY, "Stopping the session."))
        if self.close_connection:
            super().do_DELETE()
        self.stop_session()
        self.in_session.clear()

    def stop(self, notify_server=True):
        self.do_DELETE()
        if self.close_connection:
            super().shutdown(notify_server)
        else:
            super().shutdown(False)
        # if ipc_conn:
        #     self.sel.unregister(ipc_conn)
        self.sel.close()
