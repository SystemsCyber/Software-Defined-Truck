import copy
import json
import logging
import os
from logging.handlers import TimedRotatingFileHandler, QueueHandler
import multiprocessing as mp
from queue import Empty

from jsonschema import Draft7Validator, RefResolver, Validator


class Schema:
    @staticmethod
    def compile_schema(schema_name) -> Validator:
        dir = Schema.find_schema_folder()
        schema_path = os.path.join(dir, schema_name)
        with open(schema_path, 'rb') as schema_file:
            schema = json.load(schema_file)
        r = RefResolver('file:///' + dir.replace("\\", "/") + '/', schema)
        return Draft7Validator(schema, resolver=r) # type: ignore

    @staticmethod
    def find_schema_folder():
        base_dir = os.path.abspath(os.getcwd())
        base_dir = base_dir.rpartition(os.path.sep)[0]
        for root, dirs, files in os.walk(base_dir):
            for name in dirs:
                if name == "Schemas":
                    return os.path.join(root, name)
        return os.path.join(base_dir, "Schemas")

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

    @staticmethod
    def locate_log_file(log_name: str) -> str:
        base_dir = os.path.abspath(os.getcwd())
        for root, dirs, files in os.walk(base_dir):
            for name in dirs:
                if name == "Logs":
                    log_path = os.path.join(root, name)
                    return os.path.join(log_path, log_name)
        log_path = os.path.join(base_dir, "Logs")
        return os.path.join(log_path, log_name)

    @staticmethod
    def worker_configure(queue: mp.Queue, log_level=logging.DEBUG):
        root = logging.getLogger()
        root.addHandler(QueueHandler(queue))
        root.setLevel(log_level)

    @staticmethod
    def listener_configure(log_level=logging.DEBUG):
        filename = CANLayLogger.locate_log_file("controller_log")
        # Create logger object
        root = logging.getLogger()
        root.setLevel(log_level)
        # Set up handlers and formatters
        file_handler = TimedRotatingFileHandler(
            filename=filename,
            when="midnight",
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )
        # console_handler = ColoredConsoleHandler()
        formatter = logging.Formatter('%(asctime)-15s %(module)-10.10s %(levelname)s %(message)s')
        file_handler.setFormatter(formatter)
        # console_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        # root.addHandler(console_handler)

    @staticmethod
    def listen(log_queue: mp.Queue, tui_log_queue: mp.Queue, log_level=logging.DEBUG):
        CANLayLogger.listener_configure(log_level)
        while True:
            try:
                record = log_queue.get()
                if record is None:
                    break
                else:
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
                        tui_log_queue.put_nowait(
                        f"[b {color}]{record.levelname}[/b {color}] {record.msg}")
                    else:
                        tui_log_queue.put_nowait(f"{record.levelname} {record.msg}")
                    logger = logging.getLogger(record.name)
                    logger.handle(record)
            except Exception:
                import sys, traceback
                print('Whoops! Problem:', file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
