from http import HTTPStatus
import selectors
from io import BytesIO
from typing import Dict, Tuple, List
import json
import jsonschema
import logging
from collections import namedtuple
from HelperMethods import Schema, Registration

SEL = selectors.SelectorKey


class SSS3Handle:
    def __init__(self, sel: selectors.DefaultSelector, blacklist_ips: List) -> None:
        self.sel = sel
        self.blacklist_ips = blacklist_ips
        self.ECU = namedtuple("ECU", ["type", "year", "make", "model", "sn"])
        self.registration_schema = Schema.compile_schema("SSS3Registration.json")

    def do_GET(self, key: SEL, wfile: BytesIO) -> HTTPStatus:
        if self.__requester_is_client(key):
            wfile.write(self.__get_available_ECUs())
            return HTTPStatus.FOUND
        else:
            return HTTPStatus.PRECONDITION_FAILED
    
    def __requester_is_client(self, key) -> bool:
        if hasattr(key.data, "MAC") and key.data.MAC != "unknown":
            return hasattr(key.data, "type") and key.data.type == "CLIENT"
        else:
            return False

    def do_GET_register(self, key: SEL, wfile: BytesIO) -> HTTPStatus:
        wfile.write(self.registration_schema)
        return HTTPStatus.FOUND

    def do_POST_register(self, key: SEL, rfile: BytesIO) -> HTTPStatus:
        data = json.load(rfile)
        try:
            self.registration_schema.validate(data)
            return self.__register(key, data)
        except jsonschema.ValidationError:
            self.close_connection = True
            return HTTPStatus.BAD_REQUEST
    
    def do_PUT_register(self, key: SEL, rfile: BytesIO) -> HTTPStatus:
        return self.do_POST_register(key, rfile)
    
    def do_DELETE_register(self, key: SEL, wfile: BytesIO) -> HTTPStatus:
        self.close_connection = True
        return HTTPStatus.NOT_IMPLEMENTED

    def do_DELETE_session(self, key: SEL, wfile: BytesIO) -> HTTPStatus:
        self.close_connection = True
        return HTTPStatus.NOT_IMPLEMENTED

    def __get_available_ECUs(self) -> Dict:
        available = {}
        sel_map = self.sel.get_map()
        for fd in sel_map:
            key = sel_map[fd]
            if self.__is_available(key):
                available[str(fd)] = key.data.ECUs
        return available

    def __is_available(self, key: SEL) -> bool:
        if self.__not_listening_socket(key):
            return self.__is_SSS3(key) and self.__is_free(key)

    def __is_SSS3(self, key: SEL) -> bool:
        return key.type == "SSS3"

    def __is_free(self, key: SEL) -> bool:
        return not key.in_use

    def __register(self, key: SEL, data: Dict) -> HTTPStatus:
        key.data.MAC = data["MAC"]
        key.data.type = "SSS3"
        key.data.ECUs = []
        for i in data["ECUs"]:
            key.data.ECUs.append(self.ECU(
                i["type"],
                i["year"],
                i["make"],
                i["model"],
                i["sn"]
            ))
        registration_check = self.__check_registration(key)
        if registration_check == HTTPStatus.ACCEPTED:
            self.__log_registration(key)
        return registration_check

    def __check_registration(self, key: SEL) -> HTTPStatus:
        sel_map = self.sel.get_map()
        for fd in sel_map:
            if self.__not_listening_socket(sel_map[fd]):
                return self.__check_already_registered(sel_map[fd], key)

    def __not_listening_socket(self, key: SEL) -> bool:
        return hasattr(key.data, "MAC")

    def __check_already_registered(self, old_key: SEL, new_key: SEL) -> HTTPStatus:
        if old_key.fd == new_key.fd:
            # Trying to change MAC address is not allowed and connection will be
            # dropped and device will be banned.
            # else:
            if old_key.data.MAC != new_key.data.MAC:
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
            self.close_connection = True
            return HTTPStatus.CONFLICT
        else:
        # If its a different connection and different MAC we assume its a
        # different device.
            return HTTPStatus.ACCEPTED

    def __log_registration(self, key: SEL) -> None:
        msg = f'\nNew {key.data.type} connected:\n'
        msg += f'\tIP: {key.data.addr[0]}\n'
        msg += f'\tPort: {key.data.addr[1]}\n'
        msg += f'\tMAC: {key.data.MAC}\n'
        msg += "\tECUs: \n"
        for i in key.data.ECUs:
            msg += f'\t\tType: {i.type}\n'
            msg += f'\t\tYear: {i.year}\n'
            msg += f'\t\tMake: {i.make}\n'
            msg += f'\t\tModel: {i.model}\n'
            msg += f'\t\tS/N: {i.sn}\n'
        logging.info(msg)
