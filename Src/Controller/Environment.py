import copy
import json
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from multiprocessing import Event, Queue
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
        return Draft7Validator(schema, resolver=r)

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


class LogSetup:
    @staticmethod
    def findpath(log_name):
        base_dir = os.path.abspath(os.getcwd())
        for root, dirs, files in os.walk(base_dir):
            for name in dirs:
                if name == "Logs":
                    log_path = os.path.join(root, name)
                    return os.path.join(log_path, log_name)
        log_path = os.path.join(base_dir, "Logs")
        return os.path.join(log_path, log_name)

    @staticmethod
    def init_logging(log_level=logging.DEBUG) -> None:
        filename = LogSetup.findpath("controller_log")
        logging.basicConfig(
            format='%(asctime)-15s %(module)-10.10s %(levelname)s %(message)s',
            level=log_level,
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


class LogListener:
    @staticmethod
    def configure():
        filename = LogSetup.findpath("controller_log")
        root = logging.getLogger()
        file_handler = TimedRotatingFileHandler(
            filename=filename,
            when="midnight",
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )
        console_handler = ColoredConsoleHandler()
        formatter = logging.Formatter('%(asctime)-15s %(module)-10.10s %(levelname)s %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        root.addHandler(console_handler)
        root.setLevel(logging.DEBUG)

    @staticmethod
    def listen(run: Event, queue: Queue):
        LogListener.configure()
        while run.is_set():
            try:
                record = queue.get(block=True, timeout=1)
            except (Empty, InterruptedError) as ie:
                continue
            else:
                logger = logging.getLogger(record.name)
                logger.handle(record)
