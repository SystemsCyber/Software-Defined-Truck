from http import HTTPStatus, client
from ipaddress import IPv4Address
import json
import jsonschema
import selectors
from io import BytesIO
from typing import Tuple, List, Dict
import logging
from HelperMethods import Schema
from Device import Device

SEL = selectors.SelectorKey

class ClientHandle:
    def __init__(self, sel: selectors.DefaultSelector, blacklist_ips: List, multicast_ips: List) -> None:
        self.sel = sel
        self.blacklist_ips = blacklist_ips
        self.multicast_ips = multicast_ips
        self.can_port = 41665
        self.carla_port = 41664
        self.registration_schema, self.registration_schema_file = Schema.compile_schema("ClientRegistration.json")
        self.request_schema, _ = Schema.compile_schema("ClientRequest.json")
        self.session_schema, _ = Schema.compile_schema("SessionInformation.json")

    def __log_info(self, key: SEL, message: str) -> None:
        logging.info(f'{key.data.addr[0]} - - {message}')

    def __log_error(self, key: SEL, message: str) -> None:
        logging.error(f'{key.data.addr[0]} - - {message}')

    def do_GET_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.__log_info("Requested Reqistration schema.")
        wfile.write(bytes(json.dumps(self.registration_schema_file), "utf-8"))
        return HTTPStatus.FOUND

    def do_POST_register(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.__log_info("Submitted registration information.")
        try:
            data = json.load(rfile)
            self.registration_schema.validate(data)
            return self.__register(key, data)
        except jsonschema.ValidationError as ve:
            self.__log_error(key, ve)
            key.data.close_connection = True
            return HTTPStatus.BAD_REQUEST
        except json.decoder.JSONDecodeError as jde:
            self.__log_error(key, jde)
            key.data.close_connection = True
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

    def do_POST_session(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.__log_info(key, "Initiated session request.")
        try:
            data = json.loads(rfile)
            self.request_schema.validate(data)
            return self.__initiate_session_request(key, data)
        except jsonschema.ValidationError as ve:
            self.__log_error(key, ve)
            key.data.close_connection = True
            return HTTPStatus.BAD_REQUEST
        except json.decoder.JSONDecodeError as jde:
            self.__log_error(key, jde)
            key.data.close_connection = True
            return HTTPStatus.BAD_REQUEST
    
    def do_DELETE_session(self, key: SEL, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.__log_info(key, "Ended its session.")
        if not key.data.is_free:
            self.__handle_end_session(key)
            return HTTPStatus.OK
        else:
            self.__log_error(key, "Tried to end a non-existent session.")
            key.data.close_connection = True
            return HTTPStatus.EXPECTATION_FAILED

    def __handle_end_session(self, key: SEL):
        for ip in self.multicast_ips:
            if key.fd == ip["sockets"][0]:
                self.__notify_session_members(ip)

    def __register(self, key: SEL, data: Dict) -> HTTPStatus:
        key.data.MAC = data["MAC"]
        key.data.type = "CLIENT"
        registration_check = self.__check_registration(key)
        if registration_check == HTTPStatus.ACCEPTED:
            self.__log_registration(key)
        return registration_check

    def __check_registration(self, key: SEL) -> HTTPStatus:
        self.__log_info(key, "Checking registration.")
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
                self.__log_error(new_key, "Tryed to change MAC. Banning device.")
                self.blacklist_ips.append(new_key.data.addr[0])
                key.data.close_connection = True
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
                self.__log_error(new_key, "Tryed to change MAC. Banning device.")
                self.blacklist_ips.append(new_key.data.addr[0])
                key.data.close_connection = True
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
            self.__log_error(key, "Cannot initiate session request for a different client. Banning this client.")
            self.blacklist_ips.append(key.data.addr[0])
            key.data.close_connection = True
            return HTTPStatus.FORBIDDEN
        else:
            members = self.__gather_requested_devices()
            if len(members) > 1:
                self.__log_info(key, "Successfully allocated all requested devices.")
                ip = self.__find_mcast_IP(members)
                self.__log_info(key, f'Found available multicast IP address: {ip}.')
                self.__notify_session_start(members, ip)
                return HTTPStatus.CREATED
            self.__log_error(key, "Requested devices are no longer available.")
            return HTTPStatus.CONFLICT

    def __gather_requested_devices(self, key: SEL, requested: Dict) -> List:
        self.__log_info(key, "Gathering requested devices.")
        available = Device.get_available_ECUs(self.sel)
        members = [str(key.fd)]
        for fd in requested["ECUs"].keys():
            k = self.sel.get_key(int(fd))
            if fd in available:
                self.__log_info(key, f'{k.data.addr[0]} is available.')
                k.data.is_free = False
                members.append(int(fd))
            else:
                self.__log_error(key, f'{k.data.addr[0]} is not available.')
                return []
        return members

    def __find_mcast_IP(self, members: List) -> IPv4Address:
        for ip in self.multicast_ips:
            if ip["available"]:
                ip["sockets"] = members
                return ip["ip"]
                
    def __notify_session_members(self, members: List, IP = None):
        client_key = self.sel.get_key(members[0])
        self.__log_info(client_key, f'Notifying devices.')
        if IP:
            session_message = self.__create_start_message(IP)
        else:
            session_message = "DELETE * HTTP/1.1\r\n"
            session_message += "Connection: keep-alive\r\n\r\n"
            session_message = bytes(session_message)
        for device in members:
            key = self.sel.get_key(device)
            key.data.outgoing_messages.put(session_message)
            self.sel.modify(key.fileobj, selectors.EVENT_WRITE, key.data)
            msg = f'Successfully notified {key.data.addr[0]}.'
            self.__log_info(client_key, msg)

    def __create_start_message(self, IP: IPv4Address) -> bytes:
        session_information = json.dumps({
            "IP" : IP,
            "CAN_PORT": self.can_port,
            "CARLA_PORT": self.carla_port
        })
        session_message = f'POST * HTTP/1.1\r\n'
        session_message += f'Connection: keep-alive\r\n'
        session_message += f'\r\n{session_information}'
        return bytes(session_message)

    def __log_registration(self, key: SEL) -> None:
        msg = f'Successfully registered!\n'
        msg += f'\tType {key.data.type}\n'
        msg += f'\tMAC: {key.data.MAC}\n'
        self.__log_info(key, msg)