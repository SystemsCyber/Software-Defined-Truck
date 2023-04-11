import io
import logging
from multiprocessing.synchronize import Event
import multiprocessing as mp
from enum import Enum

from .Environment import CANLayLogger, OutputType as OT

class Recorder:
    def __init__(self, filename: str, mode: str = 'at') -> None:
        self.filename = filename
        self.mode = mode

    def start_recording(
        self,
        msg_queue: mp.Queue,
        stop_event: Event,
        log_queue: mp.Queue,
        log_level: int
    ) -> None:
        try:
            self.__msg_queue = msg_queue
            self.__stop_event = stop_event
            CANLayLogger.worker_configure(log_queue, log_level)
            with open(self.filename, self.mode, buffering=io.DEFAULT_BUFFER_SIZE) as file:
                self.__record(file)
        except Exception as e:
            logging.error(e, exc_info=True)
            raise e

    def __record(self, file) -> None:
        while not self.__stop_event.is_set():
            message = self.__msg_queue.get()
            if message is not None:
                self.__handle_record(file, message)
            else:
                break
        file.flush()

    def __handle_record(self, file, record: tuple) -> None:
        if record[0] == OT.CAN_MSG:
            self.__handle_can_msg(file, record[1])
        elif record[0] == OT.SIM_MSG:
            self.__handle_sim_msg(file, record[1])
        elif record[0] == OT.BUFFERED_CAN_SIM:
            for msg in record[1]:
                self.__handle_record(file, msg)
        
    def __handle_can_msg(self, file, msg: tuple) -> None:
        file.write(f"({msg[0]}) {msg[1]}#{msg[3]}\n")
    
    def __handle_sim_msg(self, file, msg: tuple) -> None:
        s = f"({msg[0]}) "
        for i in range(1, len(msg)):
            s += f"{msg[i]}"
            if i == (len(msg) - 1):
                s += "\n"
            else:
                s += " "
        file.write(s)