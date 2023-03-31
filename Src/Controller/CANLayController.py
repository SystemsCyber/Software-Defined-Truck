from __future__ import annotations

import threading as th
import logging
import selectors as sel
import ctypes as ct
from io import BytesIO
from logging.handlers import QueueHandler
import multiprocessing as mp
from multiprocessing.connection import Client, Connection, Listener, PipeConnection
from multiprocessing.sharedctypes import Synchronized
from pprint import pprint
from time import time, sleep
from types import SimpleNamespace
from typing import List

from queue import Full
from HealthReport import HealthReport, NetworkStats, NodeReport
from NetworkMatrix import NetworkMatrix
from HTTPClient import HTTPClient
from CANLayTUI import TUIOutput as TO
from rich.pretty import pprint as rpp
from rich.prompt import Prompt
from rich.table import Table
from rich import print as rp
from rich.rule import Rule
from SensorNode import COMMBlock, SensorNode, WCOMMFrame, WSenseBlock
from Environment import CANLayLogger
from CANNode import CAN_message_t
from Recorder import Recorder
from Recorder import RecordType as RT
import re


class Controller(SensorNode, HTTPClient):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._just_packed_frame = False
        self._display_mode = kwargs["_display_mode"]
        self._display_totals = kwargs["_display_totals"]
        self._can_output_buffer = []
        self._can_output_buffer_size = 20
        self._cansend_re = re.compile(
            r'^(?P<id>[0-9A-Fa-f]{3,8})(?:#|(?P<flags>#[RF]\d?|[\da-fA-F]{0,15}##[0-9A-Fa-f])?)(?P<data>(?:\.?[0-9A-Fa-f]{0,2}){0,8})$')

    def __listen(self) -> None:
        while not self.close_connection and not self._stop.is_set():
            with self.sel_lock:
                connection_events = self.sel.select(timeout=self.timeout_additive)
            for key, mask in connection_events:
                callback = key.data.callback
                callback(key)
            if self._just_packed_frame:
                self._just_packed_frame = False
            else:
                self.check_members(time())

    def __print_devices(self, available_devices: list) -> List[int]:
        # Discard any commands that have been sent to the controller
        try:
            if (self._command.poll()):
                self._command.recv()
            self._output.put((TO.DEVICES, available_devices))
            self._output.put((TO.PROMPT,
                            "Enter the numbers corresponding to the ECUs you "
                            "would like to use (comma separated): "))
            answer = self._command.recv()  # Wait for user input
            input_list = str(answer).split(',')
            return [int(i.strip()) for i in input_list]
        except (EOFError, BrokenPipeError):
            self.__stop_control_loops()
            return []

    def __request_user_input(self, available: list) -> List[int]:
        available_device_ids = [device["ID"] for device in available]
        requested = self.__print_devices(available)
        if requested == []:
            return []
        if set(requested).issubset(available_device_ids):
            if self.request_devices(requested, available):
                self._output.put(
                    (TO.NOTIFY, "Devices successfully allocated."))
                return requested
            else:
                self._output.put((TO.ERROR,
                                  "One or more of the requested devices are no longer "
                                  "available. Please select new device(s)."))
                return self.__provision_devices()
        else:
            self._output.put((TO.ERROR,
                              "One or more numbers entered do not correspond"
                              " with the available devices. Please try again."))
            return self.__request_user_input(available)

    def __provision_devices(self) -> List[int]:
        available_devices = self.get_devices()
        if len(available_devices) > 0:
            return self.__request_user_input(available_devices)
        else:
            self._output.put((TO.DEVICES, []))
            return []

    def __request_health(self) -> None:
        try:
            while not self._stop.is_set():
                # Wait until session is established, timeout after 1 second to
                # check if stop event is set
                if self._in_session.wait(1):
                    msg = COMMBlock(self.index, self.frame_number,
                                    int(time() * 1000), 3, WCOMMFrame())
                    self.health_report.update(
                        self.index,
                        ct.cast(self.network_stats.health_report,
                        ct.POINTER(ct.c_byte * (self.network_stats.size * ct.sizeof(NodeReport))))[0],
                        self.frame_number)
                    with self.health_report.lock:
                        self.health_report.counts.sim_retrans = self.times_retrans
                    self.network_stats.reset()
                    self.can_key.data.callback = self.write
                    self.can_key.data.message = bytes(msg)
                    with self.sel_lock:
                        self.sel.modify(self.can_key.fileobj,
                                        sel.EVENT_WRITE, self.can_key.data)
                    sleep(1)  # Wait 1 second before sending next health request
        except Exception as e:
            logging.debug(e, exc_info=True)

    def __accept_sim_conn(self, sim_sock: Listener) -> None:
        try:
            self._sim_conn = sim_sock.accept()
            with self.sel_lock:
                self.sel.register(self._sim_conn, sel.EVENT_READ,
                                  SimpleNamespace(callback=self.__write_signals))
        except OSError:
            logging.debug("Simulation socket closed.")

    def __write_signals(self, key: sel.SelectorKey) -> None:
        try:
            signals = key.fileobj.recv()  # type: ignore
        except EOFError:
            logging.debug("Simulator IPC socket closed.")
            self.__stop_control_loops()
        else:
            if signals:
                self._output.put((TO.SIM_MSG, signals))
                self.write(*signals)
            else:
                logging.debug("Simulator IPC socket closed.")
                self.__stop_control_loops()

    def __monitor_commands(self) -> None:
        while not self._stop.is_set():
            if self._command.poll(0.5):
                try:
                    command: str = self._command.recv()
                except EOFError:
                    logging.debug("Command IPC socket closed.")
                    self.__stop_control_loops()
                else:
                    if command is not None:
                        self.__handle_commands(command.split())
                    else:
                        logging.debug("Command IPC socket closed.")
                        self.__stop_control_loops()

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
                        self._output.put((TO.ERROR, "FD Not yet supported."))
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
                self._output.put((TO.ERROR, "Invalid CAN frame."))
                return
            self.__send_can_message(id, length, data)
            self._output.put((TO.NOTIFY, "CAN frame sent."))
            return 
                
    def __send_can_message(self, id: int, length: int, data: bytearray) -> None:
        msg = CAN_message_t()
        msg.can_id = ct.c_uint32(id)
        if length > 3:
            msg.flags.extended = ct.c_bool(True)
        msg.len = ct.c_uint8(length)
        for i in range(length):
            msg.buf[i] = ct.c_uint8(data[i])
        packed_msg = COMMBlock(
            self.index, self.frame_number, self.time_client.time_ms(), 1,
            WCOMMFrame(self.packCAN(msg)))
        self.can_key.data.callback = self.write
        self.can_key.data.message = bytes(packed_msg)
        with self.sel_lock:
            self.sel.modify(self.can_key.fileobj,
                            sel.EVENT_WRITE, self.can_key.data)
        self._output.put((TO.CAN_MSG, [(
            packed_msg.frame.canFrame.frame.can.can_id,
            packed_msg.frame.canFrame.frame.can.len,
            bytes(packed_msg.frame.canFrame.frame.can.buf).hex().upper())]))
        if self._recording:
            self._msg_queue.put((RT.CAN, (
                self.time_client.time_ms(),
                packed_msg.frame.canFrame.frame.can.can_id,
                bytes(packed_msg.frame.canFrame.frame.can.buf).hex().upper())))
    
    def __stop_control_loops(self) -> None:
        try:
            self._output.put((TO.STOP_SESSION, ""))
        except (BrokenPipeError, Full):
            pass
        finally:
            if not self._stop.is_set():
                self._stop.set()
            if self._in_session.is_set():
                self._in_session.clear()

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
        self._record_filename = record_filename
        self._recording = False
        self._msg_queue = mp.Queue()
        self._command = command
        self._output = output
        self._log_queue = log_queue
        self._log_level = log_level
        self._stop = th.Event()
        self._stop_mp = mp.Event()
        self._in_session = th.Event()
        sim_thread = th.Thread(target=self.__accept_sim_conn, args=(sim_sock,))
        ntp_thread = th.Thread(target=self.time_client.stay_updated,
                               args=(self._stop,))
        health_thread = th.Thread(target=self.__request_health)
        command_thread = th.Thread(target=self.__monitor_commands)
        try:
            sim_thread.start()
            ntp_thread.start()
            health_thread.start()
            self._output.put((TO.NOTIFY, "Connecting..."))
            if self.connect():
                self._output.put((TO.NOTIFY, "Registering..."))
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
                    self._output.put((TO.ERROR, "Failed to register."))
            else:
                self._output.put((TO.ERROR, "Failed to connect."))
        except Exception as e:
            logging.error(e, exc_info=True)
        finally:
            # Tell the user we are exiting
            self._output.put((TO.NOTIFY, "Exiting..."))
            # Tell the Network Matrix to stop
            self._stop_mp.set()
            # If we haven't set these events, do it now
            if not self._stop.is_set():
                self._stop.set()
            if self._in_session.is_set():
                self._in_session.clear()
            else:
                # The do_delete from the server should not close the application
                pass
            # Check if we setup the health report, if so stop it
            if hasattr(self, 'health_report'):
                self.health_report.stop_display()
            # Check if we setup the recording process, if so stop it
            if hasattr(self, "recorder"):
                self._msg_queue.put(None)
                self.recorder.join()
                self.recorder.close()
                while(not self._msg_queue.empty()):
                    self._msg_queue.get()
            self._msg_queue.close()
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
            if ntp_thread.is_alive():
                ntp_thread.join()
            if command_thread.is_alive():
                command_thread.join()
            if health_thread.is_alive():
                health_thread.join()
            # If somehow we got here and the TUI is still up, tell it to exit
            self._output.put((TO.EXIT, ""))
            # Disconnect from the server
            self.stop()
            # Close remaining resources
            while(not self._output.empty()):
                self._output.get()
            self._output.close()
            log_queue.close()

    def do_POST(self):  # Equivalent of start
        try:
            ip, port, request_data = super().do_POST()
            if ip:
                self._output.put((TO.NOTIFY, "Session established."))
                logging.debug(request_data)
                self.start_session(ip, port, request_data)
                self.network_stats = NetworkStats(
                    len(self.members), self.time_client)
                self.health_report = HealthReport(self.members)
                self.health_report.start_display(
                    self._stop_mp, self._output, self._log_queue, self._log_level)
                self.max_report_size = (ct.sizeof(COMMBlock) - ct.sizeof(WCOMMFrame)) + \
                    (ct.sizeof(NodeReport) * len(self.members))
                if self.max_report_size < ct.sizeof(COMMBlock):
                    self.max_report_size = ct.sizeof(COMMBlock)
                self._comm_buffer = (ct.c_byte * self.max_report_size)(0)
                if len(self._record_filename) > 0:
                    recorder = Recorder(self._record_filename)
                    self.recorder = mp.Process(
                        target=recorder.start_recording,
                        args=(self._msg_queue, self._stop_mp,
                        self._log_queue, self._log_level))
                    self.recorder.start()
                    self._recording = True
                self._can_output_buffer_size *= len(self.members)
                self._output.put((TO.START_SESSION, ""))
                self._in_session.set()
            else:
                self._output.put(
                    (TO.ERROR, "Session could not be established."))
        except TypeError as te:
            logging.error(te)

    def do_DELETE(self):  # Equivalent of stop
        self._output.put((TO.NOTIFY, "Stopping the session."))
        if self.close_connection:
            super().do_DELETE()
        self.stop_session()
        self._in_session.clear()

    def write(self, *key) -> None:
        if isinstance(key[0], sel.SelectorKey):
            super().write(key[0].data.message)
            key[0].data.callback = self.read
            with self.sel_lock:
                self.sel.modify(key[0].fileobj, sel.EVENT_READ, key[0].data)
        elif self.session_status == self.SessionStatus.Active:
            self.can_key.data.callback = self.write
            self.can_key.data.message = self.packSensorData(*key)
            if self._recording:
                self._msg_queue.put((
                    RT.SIM, (self.time_client.time_ms(), *key)))
            with self.sel_lock:
                self.sel.modify(self.can_key.fileobj,
                                sel.EVENT_WRITE, self.can_key.data)
            self._just_packed_frame = True

    def read(self, key: sel.SelectorKey) -> None:
        ct.memset(self._comm_buffer, 0, self.max_report_size)
        msg, msg_len = super().read(self._comm_buffer)
        if msg and msg.type == 1:
            self.network_stats.update(msg.index, msg_len, msg.timestamp,
                                      msg.frame.canFrame.sequence_number)
            self._can_output_buffer.append((
                msg.frame.canFrame.frame.can.can_id,
                msg.frame.canFrame.frame.can.len,
                bytes(msg.frame.canFrame.frame.can.buf).hex().upper()))
            if len(self._can_output_buffer) > self._can_output_buffer_size:
                self._output.put((TO.CAN_MSG, self._can_output_buffer.copy()))
                self._can_output_buffer.clear()
            if self._recording:
                self._msg_queue.put((RT.CAN, (
                    self.time_client.time_ms(),
                    msg.frame.canFrame.frame.can.can_id,
                    bytes(msg.frame.canFrame.frame.can.buf).hex().upper())))
        elif msg and msg.type == 4:
            # for i in range(len(self.members)):
            #     m = NodeReport.from_buffer_copy(
            #         self._comm_buffer, ((i * ct.sizeof(NodeReport)) + (ct.sizeof(COMMBlock) - ct.sizeof(WCOMMFrame))))
            #     logging.debug(
            #         f"Before memmove:\n"
            #         f"Node {msg.index} Member{0}: \n"
            #         f"packetLoss: {m.packetLoss}\n"
            #         f"latency: {m.latency.mean}\n"
            #         f"jitter: {m.jitter.mean}\n"
            #         f"goodput: {m.goodput.mean}")
            self.health_report.update(
                msg.index, self._comm_buffer, self.members[msg.index].last_seq_num)

    def stop(self, notify_server=True):
        self.do_DELETE()
        if self.close_connection:
            super().shutdown(notify_server)
        else:
            super().shutdown(False)
        # if ipc_conn:
        #     self.sel.unregister(ipc_conn)
        self.sel.close()
