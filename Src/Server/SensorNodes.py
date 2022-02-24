import json
import selectors as sel
from http import HTTPStatus
from io import BytesIO
from ipaddress import IPv4Address
from json.decoder import JSONDecodeError
from typing import Dict, List

from jsonschema import ValidationError
from jsonschema.protocols import Validator

import Routes
from Device import Device
from DeviceCollection import DeviceCollection

SELECTOR = sel.DefaultSelector
KEY = sel.SelectorKey


class SensorNodes(DeviceCollection):
    def __init__(self, _sel: SELECTOR, _multicast_ips: List) -> None:
        super().__init__(_sel, _multicast_ips)
        self.reg_schema, _ = self.compile_schema("ControllerRegistration.json")
        self.request_schema, _ = self.compile_schema("ControllerRequest.json")
        self.session_schema, _ = self.compile_schema("SessionInformation.json")

    @property
    def device_type(self) -> str:
        return "CONTROLLER"

    @property
    def registration_schema(self) -> Validator:
        return self.reg_schema

    def log_registration(self) -> str:
        msg = f'Successfully registered!\n'
        msg += f'\tType {self.key.data.type}\n'
        msg += f'\tMAC: {self.key.data.MAC}\n'
        return msg

    @Routes.add("/CONTROLLER", "GET")
    @DeviceCollection.type_required("CONTROLLER")
    def get_devices(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        return super().get_devices(key, rfile, wfile)

    @Routes.add("/CONTROLLER/REGISTER", "GET")
    def get_registration_schema(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        return super().get_registration_schema(key, rfile, wfile)

    @Routes.add("/CONTROLLER/REGISTER", "POST")
    def register(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        return super().register(key, rfile, wfile)

    @Routes.add("/CONTROLLER/REGISTER", "PUT")
    @DeviceCollection.type_required("CONTROLLER")
    def modify_registration(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        return super().modify_registration(key, rfile, wfile)

    @Routes.add("/CONTROLLER/REGISTER", "DELETE")
    @DeviceCollection.type_required("CONTROLLER")
    def unregister(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        return super().unregister(key, rfile, wfile)

    def __create_start_message(self) -> bytes:
        session_message = (
            f'POST * HTTP/1.1\r\n'
            f'Connection: keep-alive\r\n'
            f'Content-Type: application/json\r\n'
            "\r\n"
        )
        session_message = bytes(session_message, "iso-8859-1")
        return session_message

    def __find_mcast_IP(self, members: List) -> IPv4Address:
        for ip in self.multicast_ips:
            if ip["available"]:
                self.info(f'Found available multicast IP address: {ip["ip"]}.')
                ip["available"] = False
                ip["sockets"] = members
                return ip["ip"]

    def __gather_requested_devices(self, requested: List) -> List:
        self.info("Gathering requested devices.")
        available = Device.get_available_devices(self.sel, Device.is_SSSF)
        members = [{"ID": self.key.fd, "Index": 0, "Devices": ["Controller"]}]
        mapping = self.sel.get_map()
        for i in range(len(requested)):
            device = requested[i]
            key = mapping[device["ID"]]
            if device in available:
                self.info(f'{key.data.addr[0]} is available.')
                members.append({
                    "ID": device["ID"],
                    "Index": i + 1,
                    "Devices": device["Devices"]
                })
            else:
                self.error(f'{key.data.addr[0]} is not available.')
                return []
        return members

    def __initiate_session_request(self, requested: Dict, wfile: BytesIO):
        if requested["MAC"] != self.key.data.MAC:
            self.error(
                "Cannot initiate session request for a "
                "different controller. Banning this controller."
            )
            return HTTPStatus.FORBIDDEN
        else:
            members = self.__gather_requested_devices(requested["Devices"])
            if len(members) > 1:
                self.info("Successfully allocated requested devices.")
                ip = self.__find_mcast_IP(members)
                wfile.write(self.create_session_information(0, ip, members))
                message = self.__create_start_message()
                self.notify_session_members(members, message, ip)
                return HTTPStatus.CREATED
            self.error("Requested devices are no longer available.")
            return HTTPStatus.CONFLICT

    @Routes.add("/CONTROLLER/SESSION", "POST")
    @DeviceCollection.set_key
    @DeviceCollection.registration_required
    @DeviceCollection.type_required("CONTROLLER")
    def start_session(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        self.info("Initiated session request.")
        try:
            data = json.loads(rfile.read(4096))
            self.request_schema.validate(data)
            return self.__initiate_session_request(data, wfile)
        except (ValidationError, JSONDecodeError) as jde:
            self.error(jde)
            key.data.close_connection = True
            return HTTPStatus.BAD_REQUEST

    @Routes.add("/CONTROLLER/SESSION", "DELETE")
    @DeviceCollection.set_key
    @DeviceCollection.registration_required
    @DeviceCollection.type_required("CONTROLLER")
    def stop_session(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        if key.data.in_use:
            self.info("Ended its session.")
            self.handle_end_session()
            return HTTPStatus.OK
        else:
            self.error("Tried to end a non-existent session.")
            key.data.close_connection = True
            return HTTPStatus.EXPECTATION_FAILED
