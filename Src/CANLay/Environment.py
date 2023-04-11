import copy
import json
import logging
import multiprocessing as mp
import os
import sys
import traceback
from enum import Enum
from logging.handlers import QueueHandler, TimedRotatingFileHandler
from pathlib import Path

from jsonschema import Draft7Validator, RefResolver, Validator

LOGTYPE_OFF = 0
LOGTYPE_FILE = 1
LOGTYPE_CONSOLE = 2
LOGTYPE_OUTPUT = 4


class OutputType(Enum):
    OUTPUT = 0
    PROMPT = 1
    NOTIFY = 2
    ERROR = 3
    DEVICES = 4
    CAN_MSG = 5
    SIM_MSG = 6
    TOTAL_STATS = 7
    START_SESSION = 8
    STOP_SESSION = 9
    EXIT = 10
    BUFFERED_CAN_SIM = 11


class Schema:
    @staticmethod
    def compile_schema(schema_name) -> Validator:
        dir = os.path.join(str(Path(__file__).parent.parent.absolute()), "Schemas")
        schema_path = os.path.join(dir, schema_name)
        with open(schema_path, 'rb') as schema_file:
            schema = json.load(schema_file)
        r = RefResolver('file:///' + dir.replace("\\", "/") + '/', schema)
        return Draft7Validator(schema, resolver=r)  # type: ignore

# COPIED FROM: https://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output?page=1&tab=votes#tab-top


class ColoredConsoleHandler(logging.StreamHandler):

    def emit(self, record):
        # Need to make a actual copy of the record
        # to prevent altering the message for other loggers
        myrecord = copy.copy(record)
        levelno = myrecord.levelno
        if(levelno >= 50):  # CRITICAL / FATAL
            color = '\x1b[31m'  # red
        elif(levelno >= 40):  # ERROR
            color = '\x1b[31m'  # red
        elif(levelno >= 30):  # WARNING
            color = '\x1b[33m'  # yellow
        elif(levelno >= 20):  # INFO
            color = '\x1b[32m'  # green
        elif(levelno >= 10):  # DEBUG
            color = '\x1b[35m'  # pink
        else:  # NOTSET and anything else
            color = '\x1b[0m'  # normal
        myrecord.levelname = color + \
            str(myrecord.levelname) + '\x1b[0m'  # normal
        logging.StreamHandler.emit(self, myrecord)

# ------------------------------------------------------------


class CANLayLogger:

    # @staticmethod
    # def locate_log_file(log_name: str) -> str:
    #     base_dir = os.path.abspath(os.getcwd())
    #     for root, dirs, files in os.walk(base_dir):
    #         for name in dirs:
    #             if name == "Logs":
    #                 log_path = os.path.join(root, name)
    #                 return os.path.join(log_path, log_name)
    #     log_path = os.path.join(base_dir, "Logs")
    #     return os.path.join(log_path, log_name)

    @staticmethod
    def worker_configure(queue: mp.Queue, log_level=logging.DEBUG) -> None:
        root = logging.getLogger()
        add_handler = True
        if root.handlers is not None and len(root.handlers) > 0:
            for handler in root.handlers:
                if isinstance(handler, QueueHandler):
                    add_handler = False
        if add_handler:
            root.addHandler(QueueHandler(queue))
            root.setLevel(log_level)

    @staticmethod
    def listener_configure(
            log_level=logging.DEBUG,
            log_type=LOGTYPE_CONSOLE,
            log_name="CANLay.log",
            log_directory_path=None) -> None:
        # Create logger object
        root = logging.getLogger()
        root.setLevel(log_level)
        filename = log_name
        if log_directory_path:
            filename = os.path.join(log_directory_path, log_name)
        formatter = logging.Formatter(
            '%(asctime)-15s %(module)-10.10s %(levelname)s %(message)s')
        if log_type & LOGTYPE_CONSOLE:
            console_handler = ColoredConsoleHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            root.addHandler(console_handler)
        if log_directory_path:
            rotating_file_handler = TimedRotatingFileHandler(
                filename=filename,
                when="midnight",
                interval=1,
                backupCount=7,
                encoding='utf-8'
            )
            rotating_file_handler.suffix = rotating_file_handler.suffix + ".log"
            rotating_file_handler.setFormatter(formatter)
            root.addHandler(rotating_file_handler)
        elif log_type & LOGTYPE_FILE:
            file_handler = logging.FileHandler(filename)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)

    @staticmethod
    def listen(
            log_queue: mp.Queue,
            output_log_queue: mp.Queue,
            log_type=LOGTYPE_CONSOLE) -> None:
        while True:
            try:
                record = log_queue.get()
                if record is None:
                    break
                else:
                    if log_type & LOGTYPE_OUTPUT:
                        if(record.levelno >= 50):  # CRITICAL / FATAL
                            color = "bright_red"
                        elif(record.levelno >= 40):  # ERROR
                            color = "red"
                        elif(record.levelno >= 30):  # WARNING
                            color = "yellow"
                        elif(record.levelno >= 20):  # INFO
                            color = "green"
                        elif(record.levelno >= 10):  # DEBUG
                            color = "magenta"
                        else:  # NOTSET and anything else
                            color = None  # normal
                        if color is not None:
                            output_log_queue.put_nowait(
                                f"[b {color}]{record.levelname}[/b {color}] {record.msg}")
                        else:
                            output_log_queue.put_nowait(
                                f"{record.levelname} {record.msg}")
                    logger = logging.getLogger(record.name)
                    logger.handle(record)
            except Exception:
                print('Whoops! Problem:', file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
