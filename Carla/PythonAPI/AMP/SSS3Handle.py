from http import HTTPStatus
import selectors
from io import BytesIO
from typing import Dict, Tuple, List
import json
import jsonschema
import os
from collections import namedtuple

SEL = selectors.SelectorKey


class SSS3Handle:
    def __init__(self, sel: selectors.DefaultSelector, blacklist_ips: List) -> None:
        self.sel = sel
        self.blacklist_ips = blacklist_ips
        self.ECU = namedtuple("ECU", ["type", "year", "make", "model", "sn"])
        base_dir = os.path.abspath(os.getcwd())
        schema_dir = os.path.join(base_dir, "Schemas")
        registration_schema_path = os.path.join(schema_dir, "SSS3POST.json")
        with open(registration_schema_path, 'rb') as registration_schema:
            schema = json.load(registration_schema)
        resolver = jsonschema.RefResolver('file:///' + schema_dir.replace("\\", "/") + '/', schema)
        self.registration_schema = jsonschema.Draft7Validator(schema, resolver=resolver)

    def do_GET(self, key: SEL, wfile: BytesIO) -> HTTPStatus:
        if self.__device_is_registered(key):
            wfile.write(self.__get_available_ECUs())
            return HTTPStatus.FOUND
        else:
            return HTTPStatus.PRECONDITION_FAILED

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

    def __device_is_registered(self, key: SEL) -> bool:
        sel_map = self.sel.get_map()
        for fd in sel_map:
            device = sel_map[fd].data
            if hasattr(device, "MAC") and device.MAC != "unknown":
                return True
        return False

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
            # Same Connection and same MAC might mean the SSS3 is updating its
            # ECUs or it got rebooted.
            # if old_key.data.MAC == new_key.data.MAC:
            #     return HTTPStatus.ALREADY_REPORTED
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
        print(f'New {key.data.type} connected:')
        print(f'\tIP: {key.data.addr[0]}')
        print(f'\tPort: {key.data.addr[1]}')
        print(f'\tMAC: {key.data.MAC}')
        print("\tECUs: ")
        for i in key.data.ECUs:
            print(f'\t\tType: {i.type}')
            print(f'\t\tYear: {i.year}')
            print(f'\t\tMake: {i.make}')
            print(f'\t\tModel: {i.model}')
            print(f'\t\tS/N: {i.sn}')
            print()
        print()
