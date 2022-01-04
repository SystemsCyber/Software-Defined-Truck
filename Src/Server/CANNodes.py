from http import HTTPStatus
import selectors
from io import BytesIO
from typing import Dict, Tuple, List
import json
import jsonschema
import logging
from HelperMethods import Schema
from Node import Node

SEL = selectors.SelectorKey


class CANNodes:
    def __init__(self, sel: selectors.DefaultSelector, multicast_ips: List) -> None:
        self.sel = sel
        self.multicast_ips = multicast_ips
        self.registration_schema, _ = Schema.compile_schema("SSS3Registration.json")
        self.session_schema, _ = Schema.compile_schema("SessionInformation.json")

    def __log_info(self, message: str) -> None:
        logging.info(f'{self._key.data.addr[0]} - - {message}')

    def __log_error(self, message: str) -> None:
        logging.error(f'{self._key.data.addr[0]} - - {message}')

    def do_GET(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self._key = key
        self.__log_info("Requested available devices.")
        if Node.is_client(key):
            devices = json.dumps(Node.get_available_devices(self.sel))
            wfile.write(bytes(devices, "UTF-8"))
            return HTTPStatus.FOUND
        else:
            return HTTPStatus.PRECONDITION_FAILED

    def do_GET_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self._key = key
        self.__log_info("Requested Reqistration schema.")
        wfile.write(self.registration_schema)
        return HTTPStatus.FOUND

    def do_POST_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self._key = key
        self.__log_info("Submitted registration information.")
        try:
            data = json.load(rfile)
            self.registration_schema.validate(data)
            return self.__register(data)
        except jsonschema.ValidationError as ve:
            self.__log_error(ve)
            key.data.close_connection = True
            return HTTPStatus.BAD_REQUEST
        except json.decoder.JSONDecodeError as jde:
            self.__log_error(jde)
            key.data.close_connection = True
            return HTTPStatus.BAD_REQUEST
    
    def do_PUT_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self._key = key
        self.__log_info("Submitted a change in registration.")
        return self.do_POST_register(key, rfile, wfile)
    
    def do_DELETE_register(self, key: SEL, rfile = None, wfile = None) -> HTTPStatus:
        self._key = key
        self.__log_info("Unregistered.")
        if key.data.in_use:
            self.__handle_end_session()
            key.data.close_connection = True
            return HTTPStatus.OK
        else:
            key.data.close_connection = True
            return HTTPStatus.OK

    def __register(self, data: Node) -> HTTPStatus:
        self._key.data.MAC = data["MAC"]
        self._key.data.type = "SSS3"
        self._key.data.devices = data["attachedDevices"]
        registration_check = self.__check_registration()
        if registration_check == HTTPStatus.ACCEPTED:
            self.__log_registration()
        return registration_check

    def __check_registration(self) -> HTTPStatus:
        self.__log_info("Checking registration.")
        sel_map = self.sel.get_map()
        for fd in sel_map:
            if Node.is_not_listening_socket(sel_map[fd]):
                return self.__check_already_registered(sel_map[fd])

    def __check_already_registered(self, old_key: SEL) -> HTTPStatus:
        if old_key.fd == self._key.fd:
            # Trying to change MAC address is not allowed and connection will be
            # dropped and device will be banned.
            # else:
            if old_key.data.MAC != self._key.data.MAC:
                self.__log_error("Tryed to change MAC. Banning device.")
                return HTTPStatus.FORBIDDEN
            else:
                return HTTPStatus.ACCEPTED
        else:
            return self.__check_duplicates(old_key)

    def __check_duplicates(self, old_key: SEL) -> HTTPStatus:
        # Without a way to determine which connection is a real SSS3 we don't
        # know which one to ban at this time. So just drop it for now.
        if old_key.data.MAC == self._key.data.MAC:
            self.__log_error("Already is registered.")
            self._key.data.close_connection = True
            return HTTPStatus.CONFLICT
        else:
        # If its a different connection and different MAC we assume its a
        # different device.
            return HTTPStatus.ACCEPTED

    def __log_registration(self) -> None:
        msg = f'Successfully registered!\n'
        msg += f'\tType: {self._key.data.type}\n'
        msg += f'\tMAC: {self._key.data.MAC}\n'
        msg += "\tdevices: \n"
        for i in self._key.data.devices:
            msg += f'\t\tType: {i["type"]}\n'
            msg += f'\t\tYear: {i["year"]}\n'
            msg += f'\t\tMake: {i["make"]}\n'
            msg += f'\t\tModel: {i["model"]}\n'
            msg += f'\t\tS/N: {i["sn"]}\n\n'
        self.__log_info(msg)

    def __handle_end_session(self):
        message = "DELETE * HTTP/1.1\r\n"
        message += "Connection: keep-alive\r\n\r\n"
        message = bytes(message, "iso-8859-1")
        for members in self.multicast_ips:
            if self._key.fd == members["sockets"][0]:
                members["available"] = True
                self.__notify_session_members(members["sockets"], message)

    def __notify_session_members(self, members: List, message: bytes):
        self._key.data.in_use = not self._key.data.in_use
        self.__log_info(f'Notifying devices.')
        mapping = self.sel.get_map()
        for device in members[1:]:
            key = mapping[device]
            key.data.callback = key.data.write
            key.data.outgoing_messages.put(message)
            key.data.expecting_response = True
            key.data.in_use = not key.data.in_use
            self.sel.modify(key.fileobj, selectors.EVENT_WRITE, key.data)
            self.__log_info(f'Successfully notified {key.data.addr[0]}.')