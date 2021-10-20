from http import HTTPStatus, client
from ipaddress import IPv4Address
import json
import jsonschema
import selectors
from io import BytesIO
from typing import Tuple, List, Dict
import logging
from HelperMethods import Schema
from Node import Node

SEL = selectors.SelectorKey

class SensorNodes:
    def __init__(self, sel: selectors.DefaultSelector, multicast_ips: List) -> None:
        self.sel = sel
        self.multicast_ips = multicast_ips
        self.can_port = 41665
        self.carla_port = 41664
        self.registration_schema, self.registration_schema_file = Schema.compile_schema("ClientRegistration.json")
        self.request_schema, _ = Schema.compile_schema("ClientRequest.json")
        self.session_schema, _ = Schema.compile_schema("SessionInformation.json")

    def __log_info(self, message: str) -> None:
        logging.info(f'{self._key.data.addr[0]} - - {message}')

    def __log_error(self, message: str) -> None:
        logging.error(f'{self._key.data.addr[0]} - - {message}')

    def do_GET_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self._key = key
        self.__log_info("Requested Reqistration schema.")
        wfile.write(bytes(json.dumps(self.registration_schema_file), "UTF-8"))
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

    def do_POST_session(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self._key = key
        self.__log_info("Initiated session request.")
        try:
            data = json.loads(rfile.read(4096))
            self.request_schema.validate(data)
            return self.__initiate_session_request(data, wfile)
        except jsonschema.ValidationError as ve:
            self.__log_error(ve)
            key.data.close_connection = True
            return HTTPStatus.BAD_REQUEST
        except json.decoder.JSONDecodeError as jde:
            self.__log_error(jde)
            key.data.close_connection = True
            return HTTPStatus.BAD_REQUEST
    
    def do_DELETE_session(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self._key = key
        self.__log_info("Ended its session.")
        if key.data.in_use:
            self.__handle_end_session()
            return HTTPStatus.OK
        else:
            self.__log_error("Tried to end a non-existent session.")
            key.data.close_connection = True
            return HTTPStatus.EXPECTATION_FAILED

    def __handle_end_session(self):
        message = "DELETE * HTTP/1.1\r\n"
        message += "Connection: keep-alive\r\n"
        message += "Content-Length: 0\r\n\r\n"
        message = bytes(message, "iso-8859-1")
        for members in self.multicast_ips:
            list_length = len(members["sockets"]) > 0
            if list_length and self._key.fd == members["sockets"][0]:
                members["available"] = True
                self.__notify_session_members(members["sockets"], message)

    def __register(self, data: Dict) -> HTTPStatus:
        self._key.data.MAC = data["MAC"]
        self._key.data.type = "CLIENT"
        registration_check = self.__check_registration()
        if registration_check == HTTPStatus.ACCEPTED:
            self.__log_registration()
        return registration_check

    def __check_registration(self) -> HTTPStatus:
        self.__log_info("Checking registration.")
        sel_map = self.sel.get_map()
        self.duplicates = [self._key]
        for fd in sel_map:
            if Node.is_not_listening_socket(sel_map[fd]):
                return self.__check_already_registered(sel_map[fd])

    def __check_already_registered(self, old_key: SEL) -> HTTPStatus:
        if old_key.fd == self._key.fd:
            # Trying to change MAC address is not allowed and connection will be
            # dropped and device will be banned.
            if old_key.data.MAC != self._key.data.MAC:
                self.__log_error("Tryed to change MAC. Banning device.")
                return HTTPStatus.FORBIDDEN
            else:
                return HTTPStatus.ACCEPTED
        else:
            return self.__check_duplicates(old_key)

    def __check_duplicates(self, old_key: SEL) -> HTTPStatus:
        if old_key.data.MAC == self._key.data.MAC:
            if old_key.addr[0] == self._key.addr[0]:
                self.duplicates.append(old_key)
                return self.__check_number_duplicates(self.duplicates)
            else:
                self.__log_error("Tryed to change MAC. Banning device.")
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

    def __initiate_session_request(self, requested: Dict, wfile: BytesIO):
        if requested["MAC"] != self._key.data.MAC:
            self.__log_error("Cannot initiate session request for a different client. Banning this client.")
            return HTTPStatus.FORBIDDEN
        else:
            members = self.__gather_requested_devices(requested)
            if len(members) > 1:
                self.__log_info("Successfully allocated requested devices.")
                ip = self.__find_mcast_IP(members)
                self.__log_info(f'Found available multicast IP address: {ip}.')
                wfile.write(self.__create_session_information(ip, self._key.fd))
                message = self.__create_start_message()
                self.__notify_session_members(members, message, ip)
                return HTTPStatus.CREATED
            self.__log_error("Requested devices are no longer available.")
            return HTTPStatus.CONFLICT

    def __gather_requested_devices(self, requested: Dict) -> List:
        self.__log_info("Gathering requested devices.")
        available = Node.get_available_ECUs(self.sel)
        members = [self._key.fd]
        mapping = self.sel.get_map()
        for ecu in requested["ECUs"]:
            key = mapping[ecu["ID"]]
            if ecu in available:
                self.__log_info(f'{key.data.addr[0]} is available.')
                members.append(ecu["ID"])
            else:
                self.__log_error(f'{key.data.addr[0]} is not available.')
                return []
        return members

    def __create_start_message(self) -> bytes:
        session_message = (
            f'POST * HTTP/1.1\r\n'
            f'Connection: keep-alive\r\n'
            f'Content-Type: application/json\r\n'
            "\r\n"
        )
        session_message = bytes(session_message, "iso-8859-1")
        return session_message

    def __create_session_information(self, IP: IPv4Address, FD: int) -> bytes:
        session_information = json.dumps({
            "ID" : FD,
            "IP" : str(IP),
            "CAN_PORT": self.can_port,
            "CARLA_PORT": self.carla_port
        })
        session_information = bytes(session_information, "UTF-8")
        return session_information

    def __find_mcast_IP(self, members: List) -> IPv4Address:
        for ip in self.multicast_ips:
            if ip["available"]:
                ip["available"] = False
                ip["sockets"] = members
                return ip["ip"]
                
    def __notify_session_members(self, members: List, message: bytes, IP = None):
        self._key.data.in_use = not self._key.data.in_use
        self.__log_info(f'Notifying devices.')
        mapping = self.sel.get_map()
        for device in members[1:]:
            if IP:
                message += self.__create_session_information(IP, device)
            key = mapping[device]
            key.data.callback = key.data.write
            key.data.outgoing_messages.put(message)
            key.data.expecting_response = True
            key.data.in_use = not key.data.in_use
            self.sel.modify(key.fileobj, selectors.EVENT_WRITE, key.data)
            self.__log_info(f'Successfully notified {key.data.addr[0]}.')

    def __log_registration(self) -> None:
        msg = f'Successfully registered!\n'
        msg += f'\tType {self._key.data.type}\n'
        msg += f'\tMAC: {self._key.data.MAC}\n'
        self.__log_info(msg)