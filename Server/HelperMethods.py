import os
import json
import jsonschema
import logging
import copy
from typing import Dict, Tuple, List

class Schema:
    @staticmethod
    def compile_schema(schema_name) -> None:
        schema_dir = Schema.find_schema_folder()
        schema_path = os.path.join(schema_dir, schema_name)
        with open(schema_path, 'rb') as schema_file:
            schema = json.load(schema_file)
        resolver = jsonschema.RefResolver('file:///' + schema_dir.replace("\\", "/") + '/', schema)
        return jsonschema.Draft7Validator(schema, resolver=resolver), schema

    @staticmethod
    def find_schema_folder():
        base_dir = os.path.abspath(os.getcwd())
        base_dir = base_dir.rpartition(os.path.sep)[0]
        for root, dirs, files in os.walk(base_dir):
            for name in dirs:
                if name == "Schemas":
                    return os.path.join(root, name)
        return os.path.join(base_dir, "Schemas")

class LogFolder:
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
        myrecord.levelname = color + str(myrecord.levelname) + '\x1b[0m'  # normal
        logging.StreamHandler.emit(self, myrecord)
# ------------------------------------------------------------