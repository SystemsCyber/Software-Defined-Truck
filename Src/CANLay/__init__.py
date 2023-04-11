from __future__ import annotations

import logging
import multiprocessing as mp
import selectors as sel
import socket as soc
import threading as th
from enum import Enum
from io import BytesIO
from pathlib import Path
from time import sleep
from types import SimpleNamespace
from multiprocessing.connection import Listener

from .Environment import (LOGTYPE_CONSOLE, LOGTYPE_FILE, LOGTYPE_OFF,
                          LOGTYPE_OUTPUT, CANLayLogger)
from .Environment import OutputType as OT
from .HealthReport import HealthReport as healthReport
from .NetworkManager import NetworkManager as networkManager
from .Recorder import Recorder as recorder


class CANLay(networkManager):
    def __init__(self,
                 broker_host=soc.gethostname(),
                 broker_port=80,
                 retransmissions=1,
                 record=False,
                 record_filename="CANLay.txt",
                 log_level=logging.INFO,
                 log_type=LOGTYPE_CONSOLE,
                 log_filename="CANLay.log",
                 log_directory_path: str | None=None
                 ) -> None:
        """CANLay - A powerful application for testing Electronic Control Units (ECUs)

        CANLay is a tool that streamlines the testing process for ECUs. It overlays a CAN network onto the TCP/IP layer, creating a distributed hardware-in-the-loop testing environment. With CANLay, you can improve your testing process and take control of your ECU development.

        Args:
            broker_host (str, optional): The IP address or hostname of the
            broker. Defaults to host IP.
            broker_port (int, optional): The port of the broker. Defaults to
            80/443.
            retransmissions (int, optional): Number of attempts to retransit
            lost controller/SSSF messages. The number of retransmissions
            determines the interval that the program checks for lost messages.
            If retransmissions is too high then messages will be considered lost
            before they\'ve had a chance to make it to other devices. As such
            this parameter is restricted to the range 0-3. (0 = OFF, Default:
            1).
            record (bool, optional): Whether to record the session. Defaults to
            False.
            record_filename (str, optional): The name of the log file. Defaults
            to "CANLay.txt".
            log_level (int, optional): The level of logging to use. These are
            the standard python logging levels: CRITICAL = 50, FATAL = CRITICAL,
            ERROR = 40, WARNING = 30, WARN = WARNING, INFO = 20, DEBUG = 10,
            NOTSET = 0. Defaults to 1.
            log_type (int, optional): The type of logging to use. The options are OFF, FILE, CONSOLE, OUTPUT. Bitwise OR these options together if logging to multiple locations. Defaults to CONSOLE.
            log_filename (str, optional): The name of the log file. Defaults to "CANLay.log".
            log_directory_path (str, optional): The directory to store the
            rotating log files. Defaults to None.
        """
        # Validate log_level value
        if not isinstance(log_level, int):
            raise ValueError("Log level must be an integer.")
        log_level_set = {logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL}
        if log_level_set.isdisjoint({log_level}):  # Check if log_level is in log_level_set
            raise ValueError("Log level must be one of the following: DEBUG, INFO, WARNING, ERROR, CRITICAL.")
        else:
            self.__log_level = log_level

        # Validate log_type value
        if not isinstance(log_type, int):
            raise ValueError("Log type must be an integer.")
        self.__log_filename = "CANLay.log"
        is_valid_log_type = False
        self.__log_type = LOGTYPE_OFF
        if log_type == LOGTYPE_OFF:
            is_valid_log_type = True
        if log_type & LOGTYPE_FILE:
            is_valid_log_type = True
            self.__log_type = self.__log_type | LOGTYPE_FILE
            if not isinstance(log_filename, str):
                raise ValueError("Log filename must be a string.")
            if not log_directory_path:
                try:
                    with open(log_filename, "w") as file:
                        self.__log_filename = log_filename
                except IOError:
                    raise ValueError(f"Invalid log_filename: {log_filename}")
        if log_type & LOGTYPE_CONSOLE:
            is_valid_log_type = True
            self.__log_type = self.__log_type | LOGTYPE_CONSOLE
        if log_type & LOGTYPE_OUTPUT:
            is_valid_log_type = True
            self.__log_type = self.__log_type | LOGTYPE_OUTPUT
        if not is_valid_log_type:
            raise ValueError("Invalid log_type.")

        # Check if log_directory_path exists and get the full path
        self.__log_directory_path = None
        if log_directory_path:
            if not log_type & LOGTYPE_FILE:
                raise ValueError("log_directory_path can only be set if log_type is set to FILE.")
            if not isinstance(log_directory_path, str):
                raise ValueError("Log directory path must be a string.")
            log_dir_path = Path(log_directory_path)
            if not log_dir_path.is_dir():
                raise ValueError(
                    f"Invalid log_directory_path: {log_directory_path}")
            self.__log_directory_path = log_dir_path.resolve()

        if not isinstance(record, bool):
            raise ValueError("Record must be a boolean.")
        # Check if record_filename is a valid file name
        self.recording = record
        self.recorder_output: mp.Queue
        logging.debug("The value of record when initializing is: %s", record)
        if record:
            if not isinstance(record_filename, str):
                raise ValueError("Record filename must be a string.")
            try:
                with open(record_filename, "w") as file:
                    self.__record_filename = record_filename
            except IOError:
                raise ValueError(f"Invalid record_filename: {record_filename}")
        CANLayLogger.listener_configure(
            self.__log_level, self.__log_type,
            self.__log_filename, self.__log_directory_path)
        super().__init__(
            broker_host=broker_host,
            broker_port=broker_port,
            retransmissions=retransmissions)

    def __listen(self) -> None:
        while not self.close_connection and not self.stop_event.is_set():
            if self.in_session.wait(1):
                with self._sel_lock:
                    connection_events = self._sel.select(
                        timeout=self._timeout_additive)
                    for key, mask in connection_events:
                        callback = key.data.callback
                        callback(key)
                self.check_members(self.time_us() / 1000000)

    def __accept_sim_conn(self, sim_port: int, authkey: bytes) -> None:
        try:
            sim_sock = Listener(('localhost', sim_port), authkey=authkey)
            self.__sim_conn = sim_sock.accept()
            sim_sock.close()
            with self._sel_lock:
                self._sel.register(self.__sim_conn, sel.EVENT_READ,
                                   SimpleNamespace(callback=self.read_signals))
            logging.debug("Simulation connection accepted.")
        except OSError:
            logging.debug("Simulation socket closed.")

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
                    self.write_sync()
                    if init_count >= 0:
                        init_count_remaining -= 1
                        sleep(0.2)
                        continue
                    sleep(1)
        except Exception as e:
            logging.debug(e, exc_info=True)

    def __send_output_buffer(self) -> None:
        time_between_frames = round(1 / 13, 2)
        try:
            while not self.stop_event.is_set():
                if self.in_session.wait(1):
                    with self._output_buffer_lock:
                        if self._output_buffer:
                            self.output.put((OT.BUFFERED_CAN_SIM, self._output_buffer.copy()))
                        if self.recording and self._output_buffer:
                            self.recorder_output.put((OT.BUFFERED_CAN_SIM, self._output_buffer.copy()))
                        self._output_buffer.clear()
                    sleep(time_between_frames)
        except Exception as e:
            logging.debug(e, exc_info=True)

    def start(self,
              simulator=False,
              sim_port=0,
              auth_key=None,
              output_queue=None,
              log_queue=None,
              log_output_queue=None) -> None:
        """Start the CANLay workers.

        Args:
            simulator (bool): Whether to listen for simulator input.
            sim_port (int): The port to listen for simulator input on.
            auth_key (str): The authentication key to use for IPC
            authentication. If None, the processes authkey will be used. The
            challenge repsonse mechanism is the python Listener/Client
            authentication mechanism.
            output_queue (Queue): The queue to send output to. If None, a new
            queue is created.
            log_queue (Queue): The queue to send log messages to. If None, a
            new queue is created.
            log_output_queue (Queue): The queue to send log messages to be
            printed such as to a TUI. If None, a new queue is created.
        """
        self.__auth_key = mp.current_process().authkey if auth_key is None else auth_key
        self.__log_queue = mp.Queue() if log_queue is None else log_queue
        self.output = mp.Queue() if output_queue is None else output_queue
        self.__log_output_queue = mp.Queue() if log_output_queue is None else log_output_queue
        self.recorder_output = mp.Queue()
        self.stop_event = th.Event()
        self.in_session = th.Event()
        self.__stop_mp = mp.Event()
        if not self.__log_type == LOGTYPE_OFF:
            self.__log_listener = mp.Process(
                target=CANLayLogger.listen,
                args=(self.__log_queue, self.__log_output_queue, self.__log_type))
            self.__log_listener.start()
        CANLayLogger.worker_configure(self.__log_queue, self.__log_level)
        self.__ptp_thread = th.Thread(target=self.__send_sync_loop)
        self.__health_thread = th.Thread(target=self.__request_health_loop)
        self.__listen_thread = th.Thread(target=self.__listen)
        self.__output_thread = th.Thread(target=self.__send_output_buffer)
        try:
            if simulator:
                self.__sim_thread = th.Thread(
                    target=self.__accept_sim_conn, args=(sim_port, self.__auth_key))
                self.__sim_thread.start()
            self.__ptp_thread.start()
            self.__health_thread.start()
            self.__listen_thread.start()
            self.__output_thread.start()
            self.output.put((OT.NOTIFY, "Connecting..."))
            if self.connect():
                self.output.put((OT.NOTIFY, "Registering..."))
                if self.register():
                    self.output.put((OT.NOTIFY, "Connected."))
                    return
                else:
                    self.output.put((OT.ERROR, "Failed to register."))
            else:
                self.output.put((OT.ERROR, "Failed to connect."))
        except Exception as e:
            logging.error(e, exc_info=True)

    def stop(self, notify_server=True):
        # Tell the user we are exiting
        self.output.put((OT.NOTIFY, "Exiting..."))
        # Tell the Network Matrix to stop
        self.__stop_mp.set()
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
        if hasattr(self, '__sim_conn'):
            # Close the socket
            self._sel.unregister(self.__sim_conn)
            self.__sim_conn.close()
        # If the threads are still running, wait for them to finish
        if hasattr(self, '__sim_thread'):
            if self.__sim_thread.is_alive():
                self.__sim_thread.join()
        if self.__ptp_thread.is_alive():
            self.__ptp_thread.join()
        if self.__output_thread.is_alive():
            self.__output_thread.join()
        if self.__health_thread.is_alive():
            self.__health_thread.join()
        if self.__listen_thread.is_alive():
            self.__listen_thread.join()
        # If somehow we got here and the TUI is still up, tell it to exit
        self.output.put((OT.EXIT, ""))
        # Disconnect from the server
        self.do_DELETE()
        super().shutdown(notify_server)
        # Close the selector
        self._sel.close()
        # Close remaining resources
        while (not self.output.empty()):
            self.output.get()
        self.output.close()
        # Tell the log listener to shut down
        self.__log_queue.put_nowait(None)
        self.__log_queue.close()
        # Clear the log output queue
        while (not self.__log_output_queue.empty()):
            self.__log_output_queue.get()
        self.__log_output_queue.close()
        # Wait for the log listener to finish shutting down
        if not self.__log_type == LOGTYPE_OFF:
            self.__log_listener.join(2)
            self.__log_listener.close()

    def start_session(self) -> None:
        if hasattr(self, "response_data") and self.response_data:
            with self._sel_lock:
                self._sel.modify(
                    self.ctrl.sock, sel.EVENT_READ,
                    SimpleNamespace(
                    callback=self.receive_SSE, outgoing_message=None))
            with BytesIO(self.response_data) as self.rfile:
                self.do_POST()
        else:
            raise Exception("Request devices before starting a session.")

    def stop_session(self) -> None:
        return self.do_DELETE()

    def do_POST(self):  # Equivalent of start
        try:
            ip, port, request_data = super().do_POST()
            if ip:
                self.output.put((OT.NOTIFY, "Session established."))
                logging.debug(request_data)
                super().start_session(ip, port, request_data)
                self.health_report = healthReport(self.members)
                self.health_report.start_display(
                    self.__stop_mp, self.output, self.__log_queue, self.__log_level)
                logging.debug(f"The value for recording is: {self.recording}")
                if self.recording:
                    logging.debug("Starting recording process.")
                    rec = recorder(self.__record_filename)
                    self.recorder = mp.Process(
                        target=rec.start_recording,
                        args=(self.recorder_output, self.__stop_mp,
                              self.__log_queue, self.__log_level))
                    self.recorder.start()
                self.in_session.set()
            else:
                self.output.put(
                    (OT.ERROR, "Session could not be established."))
        except TypeError as te:
            logging.error(te)

    def do_DELETE(self):  # Equivalent of stop
        self.output.put((OT.NOTIFY, "Stopping the session."))
        if self.close_connection:
            super().do_DELETE()
        super().stop_session()
        self.in_session.clear()
