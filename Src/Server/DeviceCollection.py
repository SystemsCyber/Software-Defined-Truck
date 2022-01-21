import abc
import json
import logging
import os
import selectors as sel
from functools import wraps
from http import HTTPStatus
from io import BytesIO
from ipaddress import IPv4Address
from json.decoder import JSONDecodeError
from types import FunctionType
from typing import List, Tuple

import jsonschema
from jsonschema import ValidationError
from jsonschema.protocols import Validator

from Device import Device

SELECTOR = sel.DefaultSelector
KEY = sel.SelectorKey


class DeviceCollection:
    __metaclass__ = abc.ABCMeta

    def __init__(self, _sel: SELECTOR, _multicast_ips: List) -> None:
        self.sel = _sel
        self.multicast_ips = _multicast_ips
        self.schema_dir = self.__find_schema_folder()
        self.key = KEY
        self.can_port = 41665

    def __find_schema_folder(self) -> str:
        base_dir = os.path.abspath(os.getcwd())
        base_dir = base_dir.rpartition(os.path.sep)[0]
        for root, dirs, files in os.walk(base_dir):
            for name in dirs:
                if name == "Schemas":
                    return os.path.join(root, name)
        return os.path.join(base_dir, "Schemas")

    def compile_schema(self, schema_name) -> Tuple[Validator, object]:
        schema_path = os.path.join(self.schema_dir, schema_name)
        with open(schema_path, 'rb') as schema_file:
            schema = json.load(schema_file)
        resolver = jsonschema.RefResolver(
            'file:///' + self.schema_dir.replace("\\", "/") + '/', schema)
        return jsonschema.Draft7Validator(schema, resolver=resolver), schema

    def set_key(func: FunctionType) -> FunctionType:
        @wraps(func)
        def wrapper(self, key: KEY, *args):
            self.key = key
            return func(self, key, *args)
        return wrapper

    def registration_required(func: FunctionType) -> FunctionType:
        @wraps(func)
        def wrapper(self, key: KEY, *args):
            if hasattr(key.data, "MAC") and key.data.MAC:
                return func(self, key, *args)
            else:
                return HTTPStatus.PRECONDITION_FAILED
        return wrapper

    def type_required(type: str) -> FunctionType:
        def decorator_wrapper(func: FunctionType) -> FunctionType:
            @wraps(func)
            def wrapper(self, key: KEY, *args):
                if hasattr(key.data, "type") and key.data.type == type:
                    return func(self, key, *args)
                else:
                    return HTTPStatus.PRECONDITION_FAILED
            return wrapper
        return decorator_wrapper

    def debug(self, message: str) -> None:
        logging.debug(f'{self.key.data.addr[0]} - {message}')

    def info(self, message: str) -> None:
        logging.info(f'{self.key.data.addr[0]} - {message}')

    def warning(self, message: str) -> None:
        logging.warning(f'{self.key.data.addr[0]} - {message}')

    def error(self, message: str) -> None:
        logging.error(f'{self.key.data.addr[0]} - {message}')

    @property
    @abc.abstractmethod
    def device_type(self) -> str:
        return

    @property
    @abc.abstractmethod
    def registration_schema(self) -> Validator:
        return

    @abc.abstractmethod
    def log_registration(self) -> str:
        return

    @set_key
    @registration_required
    def get_devices(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.info(f"Requested available {__name__}.")
        is_type = getattr(Device, "is_" + self.device_type)
        devices = json.dumps(Device.get_available_devices(self.sel, is_type))
        wfile.write(bytes(devices, "UTF-8"))
        return HTTPStatus.FOUND

    @set_key
    def get_registration_schema(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.info("Requested Reqistration schema.")
        wfile.write(self.registration_schema)
        return HTTPStatus.FOUND

    def __check_number_duplicates(self, duplicates: List[KEY]) -> HTTPStatus:
        if len(duplicates) > 5:
            return HTTPStatus.CONFLICT
        else:
            return HTTPStatus.ACCEPTED

    def __check_duplicates(self, old_key: KEY) -> HTTPStatus:
        if old_key.data.MAC == self.key.data.MAC:
            if self.device_type == "SSSF":
                # Without a way to determine which connection is a real SSSF we don't
                # know which one to ban at this time. So just drop it for now.
                self.error("Already is registered.")
                self.key.data.close_connection = True
                return HTTPStatus.CONFLICT
            elif old_key.addr[0] == self.key.addr[0]:
                self.duplicates.append(old_key)
                return self.__check_number_duplicates(self.duplicates)
            else:
                self.error("Tried to change MAC. Banning device.")
                return HTTPStatus.FORBIDDEN
        else:
            # If its a different connection and different MAC we assume its a
            # different device.
            return HTTPStatus.ACCEPTED

    def __check_already_registered(self, old_key: KEY) -> HTTPStatus:
        if old_key.fd == self.key.fd:
            # Trying to change MAC address is not allowed and connection will be
            # dropped and device will be banned.
            if old_key.data.MAC != self.key.data.MAC:
                self.error("Tried to change MAC. Banning device.")
                return HTTPStatus.FORBIDDEN
            else:
                return HTTPStatus.ACCEPTED
        else:
            return self.__check_duplicates(old_key)

    def __check_registration(self) -> HTTPStatus:
        self.info("Checking registration.")
        sel_map = self.sel.get_map()
        if self.device_type == "CONTROLLER":
            self.duplicates = [self.key]
        for fd in sel_map:
            if Device.is_not_listening_socket(sel_map[fd]):
                return self.__check_already_registered(sel_map[fd])

    def __register(self, data: Device) -> HTTPStatus:
        self.key.data.MAC = data["MAC"]
        self.key.data.type = self.device_type
        if self.device_type == "SSSF":
            self.key.data.devices = data["AttachedDevices"]
        registration_check = self.__check_registration()
        if registration_check == HTTPStatus.ACCEPTED:
            self.info(self.log_registration())
        return registration_check

    @set_key
    def register(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.info("Submitted registration information.")
        try:
            data = json.load(rfile)
            self.registration_schema.validate(data)
            return self.__register(data)
        except (ValidationError, JSONDecodeError) as jde:
            self.error(jde)
            key.data.close_connection = True
            return HTTPStatus.BAD_REQUEST

    @set_key
    @registration_required
    def modify_registration(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.info("Submitted a change in registration.")
        return self.register(key, rfile, wfile)

    def create_session_information(self, index: int, ip: IPv4Address, members: List) -> bytes:
        session_information = json.dumps({
            "ID": members[index]["ID"],
            "Index": members[index]["Index"],
            "IP": str(ip),
            "Port": self.can_port,
            "Devices": members
        })
        session_information = bytes(session_information, "UTF-8")
        return session_information

    def notify_session_members(self, members: List, message: bytes, IP=None):
        self.key.data.in_use = not self.key.data.in_use
        self.info(f'Notifying devices.')
        mapping = self.sel.get_map()
        for i in range(1, len(members)):
            msg = message
            if IP:
                msg += self.create_session_information(i, IP, members)
            key = mapping[members[i]["ID"]]
            key.data.callback = key.data.write
            key.data.outgoing_messages.put(msg)
            key.data.expecting_response = True
            key.data.in_use = not key.data.in_use
            self.sel.modify(key.fileobj, sel.EVENT_WRITE, key.data)
            self.info(f'Successfully notified {key.data.addr[0]}.')

    def handle_end_session(self):
        message = "DELETE * HTTP/1.1\r\n"
        message += "Connection: keep-alive\r\n"
        message += "Content-Length: 0\r\n\r\n"
        message = bytes(message, "iso-8859-1")
        for ip in self.multicast_ips:
            members = len(ip["sockets"]) > 0
            if members and self.key.fd == ip["sockets"][0]["ID"]:
                ip["available"] = True
                self.notify_session_members(ip["sockets"], message)

    @set_key
    @registration_required
    def unregister(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.info("Unregistered.")
        if key.data.in_use:
            self.handle_end_session()
            key.data.close_connection = True
            return HTTPStatus.OK
        else:
            key.data.close_connection = True
            return HTTPStatus.OK
