import selectors as sel
from http import HTTPStatus
from io import BytesIO

from jsonschema.protocols import Validator

import Routes
from DeviceCollection import DeviceCollection

SELECTOR = sel.DefaultSelector
KEY = sel.SelectorKey


class CANNodes(DeviceCollection):
    def __init__(self, _sel: SELECTOR, _multicast_ips: list) -> None:
        super().__init__(_sel, _multicast_ips)
        self.reg_schema, _ = self.compile_schema("SSSFRegistration.json")
        self.session_schema, _ = self.compile_schema("SessionInformation.json")

    @property
    def device_type(self) -> str:
        return "SSSF"

    @property
    def registration_schema(self) -> Validator:
        return self.reg_schema

    def log_registration(self) -> str:
        msg = f'Successfully registered!\n'
        msg += f'\tType: {self.key.data.type}\n'
        msg += f'\tMAC: {self.key.data.MAC}\n'
        msg += "\tDevices: \n"
        for i in self.key.data.devices:
            msg += f'\t\tType: {i["Type"]}\n'
            msg += f'\t\tYear: {i["Year"]}\n'
            msg += f'\t\tMake: {i["Make"]}\n'
            msg += f'\t\tModel: {i["Model"]}\n'
            msg += f'\t\tS/N: {i["SN"]}\n\n'
        return msg

    @Routes.add("/SSSF", "GET")
    @DeviceCollection.type_required("CONTROLLER")
    def get_devices(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        return super().get_devices(key, rfile, wfile)

    @Routes.add("/SSSF/REGISTER", "GET")
    def get_registration_schema(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        return super().get_registration_schema(key, rfile, wfile)

    @Routes.add("/SSSF/REGISTER", "POST")
    def register(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        return super().register(key, rfile, wfile)

    @Routes.add("/SSSF/REGISTER", "PUT")
    @DeviceCollection.type_required("SSSF")
    def modify_registration(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        return super().modify_registration(key, rfile, wfile)

    @Routes.add("/SSSF/REGISTER", "DELETE")
    @DeviceCollection.type_required("SSSF")
    def unregister(self, key: KEY, rfile: BytesIO, wfile: BytesIO) -> HTTPStatus:
        return super().unregister(key, rfile, wfile)
