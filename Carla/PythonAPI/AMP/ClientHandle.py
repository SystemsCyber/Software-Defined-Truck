from http import HTTPStatus
import json
import jsonschema
import selectors
from io import BytesIO
from typing import Tuple, List, Dict
import logging
from HelperMethods import Schema, Device

SEL = selectors.SelectorKey

class ClientHandle:
    def __init__(self, sel: selectors.DefaultSelector, blacklist_ips: List) -> None:
        self.sel = sel
        self.blacklist_ips = blacklist_ips
        self.registration_schema, self.registration_schema_file = Schema.compile_schema("ClientRegistration.json")
        self.request_schema, _ = Schema.compile_schema("ClientRequest.json")
        self.session_schema, _ = Schema.compile_schema("SessionInformation.json")

    def do_GET_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        wfile.write(bytes(json.dumps(self.registration_schema_file), "utf-8"))
        return HTTPStatus.FOUND

    def do_POST_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        try:
            data = json.load(rfile)
            self.registration_schema.validate(data)
            return self.__register(key, data)
        except jsonschema.ValidationError:
            self.close_connection = True
            return HTTPStatus.BAD_REQUEST
        except json.decoder.JSONDecodeError:
            self.close_connection = True
            return HTTPStatus.BAD_REQUEST
    
    def do_PUT_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        return self.do_POST_register(key, rfile, wfile)
    
    def do_DELETE_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.close_connection = True
        return HTTPStatus.NOT_IMPLEMENTED

    def do_POST_session(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        try:
            data = json.loads(rfile)
            self.request_schema.validate(data)
            return self.__initiate_session_request(key, data)
        except jsonschema.ValidationError:
            self.close_connection = True
            return HTTPStatus.BAD_REQUEST
        except json.decoder.JSONDecodeError:
            self.close_connection = True
            return HTTPStatus.BAD_REQUEST
    
    def do_DELETE_session(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
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
            if Device.is_not_listening_socket(sel_map[fd]):
                return self.__check_already_registered(sel_map[fd], key)

    def __check_already_registered(self, old_key: SEL, new_key: SEL) -> HTTPStatus:
        if old_key.fd == new_key.fd:
            # Trying to change MAC address is not allowed and connection will be
            # dropped and device will be banned.
            if old_key.data.MAC != new_key.data.MAC:
                self.blacklist_ips.append(new_key.data.addr[0])
                self.close_connection = True
                return HTTPStatus.FORBIDDEN
            else:
                return HTTPStatus.ACCEPTED
        else:
            return self.__check_duplicates(old_key, new_key)

    def __check_duplicates(self, old_key: SEL, new_key: SEL) -> HTTPStatus:
        if old_key.data.MAC == new_key.data.MAC:
            if old_key.addr[0] == new_key.addr[0]:
                self.duplicates.append(old_key)
                return self.__check_number_duplicates(self.duplicates)
            else:
                self.blacklist_ips.append(new_key.data.addr[0])
                self.close_connection = True
                return HTTPStatus.FORBIDDEN
        else:
        # If its a different connection and different MAC we assume its a
        # different device.
            return HTTPStatus.ACCEPTED

    def __check_number_duplicates(self, duplicates: List[SEL]) -> HTTPStatus:
        if len(duplicates) > 5:
            return HTTPStatus.CONFLICT
        else:
            return HTTPStatus.ACCEPTED

    def __initiate_session_request(self, key: SEL, requested: Dict):
        if requested["MAC"] != key.data.MAC:
            self.blacklist_ips.append(key.data.addr[0])
            self.close_connection = True
            return HTTPStatus.FORBIDDEN
        else:
            members = self.__gather_requested_devices()
            if len(members) > 1:
                mcast_pair = self.__find_mcast_pair()
                self.__notify_session_members(members, mcast_pair)
                return HTTPStatus.CREATED
            return HTTPStatus.CONFLICT

    def __gather_requested_devices(self, key: SEL, requested: Dict):
        available = Device.get_available_ECUs(self.sel)
        members = [str(key.fd)]
        for fd in requested["ECUs"].keys():
            if fd in available:
                members.append(fd)
            else:
                return []
        return members

    def __find_mcast_pair(self):
        return

    def __notify_session_members(self, members):
        return

    def __log_registration(self, key: SEL) -> None:
        msg = f'\nNew {key.data.type} connected:\n'
        msg +=f'\tIP: {key.data.addr[0]}\n'
        msg +=f'\tPort: {key.data.addr[1]}\n'
        msg +=f'\tMAC: {key.data.MAC}\n'
        logging.info(msg)