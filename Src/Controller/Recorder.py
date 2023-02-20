import multiprocessing as mp
import logging
from Environment import CANLayLogger
from enum import Enum
import io

class RecordType(Enum):
    CAN = 0
    SIM = 1

class Recorder:
    def __init__(self, filename: str, mode: str = 'at') -> None:
        self.filename = filename
        self.mode = mode

    def start_recording(
        self,
        msg_queue: mp.Queue,
        stop_event,
        log_queue: mp.Queue,
        log_level: int
    ) -> None:
        try:
            self.msg_queue = msg_queue
            self.stop_event = stop_event
            CANLayLogger.worker_configure(log_queue, log_level)
            with open(self.filename, self.mode, buffering=io.DEFAULT_BUFFER_SIZE) as file:
                self.__record(file)
        except Exception as e:
            logging.error(e, exc_info=True)
            raise e

    def __record(self, file) -> None:
        while not self.stop_event.is_set():
            message = self.msg_queue.get()
            if message is not None:
                self.__handle_record(file, message)
            else:
                break
        file.flush()

    def __handle_record(self, file, record: tuple) -> int:
        if record[0] == RecordType.CAN:
            return file.write(
                f"({record[1][0]}) {record[1][1]:x}#{record[1][2]}\n")
        elif record[0] == RecordType.SIM:
            s = f"({record[1][0]}) "
            for i in range(1, len(record[1])):
                s += f"{record[1][i]}"
                if i == (len(record[1]) - 1):
                    s += "\n"
                else:
                    s += " "
            return file.write(s)
        else:
            return 0