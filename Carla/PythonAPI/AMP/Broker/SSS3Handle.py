from http import HTTPStatus
import selectors
from io import BytesIO
from typing import Dict, Tuple, List
import json
import jsonschema
import logging
from collections import namedtuple
from HelperMethods import Schema
from Device import Device

SEL = selectors.SelectorKey


class SSS3Handle:
    def __init__(self, sel: selectors.DefaultSelector, blacklist_ips: List) -> None:
        self.sel = sel
        self.blacklist_ips = blacklist_ips
        self.ECU = namedtuple("ECU", ["type", "year", "make", "model", "sn"])
        self.session = namedtuple("Session", ["CARLA_MCAST", "CAN_MCAST"])
        self.registration_schema, _ = Schema.compile_schema("SSS3Registration.json")
        self.session_schema, _ = Schema.compile_schema("SessionInformation.json")

    def __log_info(self, key: SEL, message: str) -> None:
        logging.info(f'{key.data.addr[0]} - - {message}')

    def __log_error(self, key: SEL, message: str) -> None:
        logging.error(f'{key.data.addr[0]} - - {message}')

    def do_GET(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.__log_info("Requested available devices.")
        if Device.is_client(key):
            wfile.write(Device.get_available_ECUs(self.sel))
            return HTTPStatus.FOUND
        else:
            return HTTPStatus.PRECONDITION_FAILED

    def do_GET_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.__log_info("Requested Reqistration schema.")
        wfile.write(self.registration_schema)
        return HTTPStatus.FOUND

    def do_POST_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.__log_info("Submitted registration information.")
        try:
            data = json.load(rfile)
            self.registration_schema.validate(data)
            return self.__register(key, data)
        except jsonschema.ValidationError as ve:
            self.__log_error(key, ve)
            self.close_connection = True
            return HTTPStatus.BAD_REQUEST
        except json.decoder.JSONDecodeError as jde:
            self.__log_error(key, jde)
            self.close_connection = True
            return HTTPStatus.BAD_REQUEST
    
    def do_PUT_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.__log_info(key, "Submitted a change in registration.")
        return self.do_POST_register(key, rfile, wfile)
    
    def do_DELETE_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.__log_info(key, "Unregistered.")
        if key.data.is_free:
            key.data.close_connection = True
            return HTTPStatus.OK
        else:
            self.__handle_end_session(key)
            key.data.close_connection = True
            return HTTPStatus.OK

    def __register(self, key: SEL, data: Dict) -> HTTPStatus:
        key.data.MAC = data["MAC"]
        key.data.type = "SSS3"
        key.data.ECUs = [self.ECU(**i) for i in data["ECUs"]]
        registration_check = self.__check_registration(key)
        if registration_check == HTTPStatus.ACCEPTED:
            self.__log_registration(key)
        return registration_check

    def __check_registration(self, key: SEL) -> HTTPStatus:
        self.__log_info(key, "Checking registration.")
        sel_map = self.sel.get_map()
        for fd in sel_map:
            if Device.is_not_listening_socket(sel_map[fd]):
                return self.__check_already_registered(sel_map[fd], key)

    def __check_already_registered(self, old_key: SEL, new_key: SEL) -> HTTPStatus:
        if old_key.fd == new_key.fd:
            # Trying to change MAC address is not allowed and connection will be
            # dropped and device will be banned.
            # else:
            if old_key.data.MAC != new_key.data.MAC:
                self.__log_error(new_key, "Tryed to change MAC. Banning device.")
                self.blacklist_ips.append(new_key.data.addr[0])
                self.close_connection = True
                return HTTPStatus.FORBIDDEN
            else:
                return HTTPStatus.ACCEPTED
        else:
            return self.__check_duplicates(old_key, new_key)

    def __check_duplicates(self, old_key: SEL, new_key: SEL) -> HTTPStatus:
        # Without a way to determine which connection is a real SSS3 we don't
        # know which one to ban at this time. So just drop it for now.
        if old_key.data.MAC == new_key.data.MAC:
            self.__log_error(new_key, "Already is registered.")
            self.close_connection = True
            return HTTPStatus.CONFLICT
        else:
        # If its a different connection and different MAC we assume its a
        # different device.
            return HTTPStatus.ACCEPTED

    def __log_registration(self, key: SEL) -> None:
        msg = f'Successfully registered!\n'
        msg += f'\tType: {key.data.type}\n'
        msg += f'\tMAC: {key.data.MAC}\n'
        msg += "\tECUs: \n"
        for i in key.data.ECUs:
            msg += f'\t\tType: {i.type}\n'
            msg += f'\t\tYear: {i.year}\n'
            msg += f'\t\tMake: {i.make}\n'
            msg += f'\t\tModel: {i.model}\n'
            msg += f'\t\tS/N: {i.sn}\n\n'
        self.__log_info(key, msg)

    def __notify_session_members(self, members: List):
        client_key = self.sel.get_key(members[0])
        self.__log_info(client_key, f'Notifying devices.')
        session_message = "DELETE * HTTP/1.1\r\n"
        session_message += "Connection: keep-alive\r\n\r\n"
        session_message = bytes(session_message)
        for device in members:
            key = self.sel.get_key(device)
            key.data.outgoing_messages.put(session_message)
            self.sel.modify(key.fileobj, selectors.EVENT_WRITE, key.data)
            msg = f'Successfully notified {key.data.addr[0]}.'
            self.__log_info(client_key, msg)