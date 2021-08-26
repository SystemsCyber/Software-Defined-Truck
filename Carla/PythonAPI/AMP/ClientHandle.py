from http import HTTPStatus
import json
import jsonschema
import selectors
from io import BytesIO
from typing import Tuple, List, Dict

SEL = selectors.SelectorKey

class ClientHandle:
    def __init__(self, sel: selectors.DefaultSelector, blacklist_ips: List) -> None:
        self.sel = sel
        self.blacklist_ips = blacklist_ips
        with open("Schemas\ClientPOST.json", 'rb') as registration_schema:
            self.registration_schema = json.load(registration_schema)

    def do_GET_register(self, key: SEL, wfile: BytesIO) -> HTTPStatus:
        wfile.write(self.registration_schema)
        return HTTPStatus.FOUND

    def do_POST_register(self, key: SEL, rfile: BytesIO) -> HTTPStatus:
        data = json.load(rfile)
        try:
            jsonschema.validate(data, self.registration_schema)
            return self.__register(key, data)
        except jsonschema.ValidationError:
            self.close_connection = True
            return HTTPStatus.BAD_REQUEST
    
    def do_PUT_register(self, key: SEL, rfile: BytesIO) -> HTTPStatus:
        return self.do_POST_register(key, rfile)
    
    def do_DELETE_register(self, key: SEL, wfile: BytesIO) -> HTTPStatus:
        self.close_connection = True
        return HTTPStatus.NOT_IMPLEMENTED

    def do_POST_session(self, key: SEL, wfile: BytesIO) -> HTTPStatus:
        return HTTPStatus.NOT_IMPLEMENTED

    def do_DELETE_session(self, key: SEL, wfile: BytesIO) -> HTTPStatus:
        self.close_connection = True
        return HTTPStatus.NOT_IMPLEMENTED

    def __register(self, key: SEL, data: Dict) -> HTTPStatus:
        key.data.MAC = data["MAC"]
        key.data.type = "CLIENT"

        registration_check = self.__check_registration(key)
        if registration_check == HTTPStatus.ACCEPTED:
            self.__log_registration(key)
        return registration_check

    def __check_registration(self, key: SEL) -> HTTPStatus:
        sel_map = self.sel.get_map()
        self.duplicates = [key]
        for fd in sel_map:
            if self.__not_listening_socket(sel_map[fd]):
                return self.__check_already_registered(sel_map[fd], key)

    def __not_listening_socket(self, key: SEL) -> bool:
        return hasattr(key.data, "MAC")

    def __check_already_registered(self, old_key: SEL, new_key: SEL) -> HTTPStatus:
        if old_key.fd == new_key.fd:
            if old_key.data.MAC == new_key.data.MAC:
                return HTTPStatus.ALREADY_REPORTED
            # Trying to change MAC address is not allowed and connection will be
            # dropped and device will be banned.
            else:
                self.blacklist_ips.append(new_key.data.addr[0])
                self.close_connection = True
                return HTTPStatus.FORBIDDEN
        else:
            return self.__check_duplicates(old_key, new_key)

    def __check_duplicates(self, old_key: SEL, new_key: SEL) -> HTTPStatus:
        if old_key.data.MAC == new_key.data.MAC:
            self.duplicates.append(old_key)
            return self.__check_number_duplicates(self.duplicates)
        else:
        # If its a different connection and different MAC we assume its a
        # different device.
            return HTTPStatus.ACCEPTED

    def __check_number_duplicates(self, duplicates: List[SEL]) -> HTTPStatus:
        if len(duplicates) > 5:
            return HTTPStatus.CONFLICT
        else:
            return HTTPStatus.ACCEPTED

    def __log_registration(self, key: SEL) -> None:
        print(f'New {key.data.type} connected:')
        print(f'\tIP: {key.data.addr[0]}')
        print(f'\tPort: {key.data.addr[1]}')
        print(f'\tMAC: {key.data.MAC}')
        print()