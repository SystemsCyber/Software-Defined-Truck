import json
import logging
import selectors as sel
import socket as soc
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from ipaddress import AddressValueError, IPv4Address
from json.decoder import JSONDecodeError
from time import sleep

from jsonschema import ValidationError, Validator

from CANNode import CANNode
from Environment import Schema


class HTTPClient(CANNode, BaseHTTPRequestHandler):
    def __init__(self, *args, _server_ip=soc.gethostname(), **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if _server_ip != "127.0.0.1":
            self.__server_ip = _server_ip
        else:
            self.__server_ip = soc.gethostname()
        self.protocol_version = "HTTP/1.1"
        self.close_connection = False

        self.request_schema = Validator
        self.sessions_schema = Validator

    # Overrides for the parent functions

    def log_error(self, format, *args):
        logging.error("%s - %s\n" % ("SERVER", format % args))

    def log_message(self, format, *args):
        logging.info("%s - %s\n" % ("SERVER", format % args))

    # ----------------------------------

    def connect(self, retry=True) -> bool:
        # Cannot put these schema lines in init due to file sharing issues that
        # occur between the jsonschema library and multiprocess library
        self.request_schema = Schema.compile_schema("RequestDevices.json")
        self.session_schema = Schema.compile_schema("SessionInformation.json")
        try:
            logging.info("Connecting to the server.")
            self.ctrl = HTTPConnection(self.__server_ip)
            self.ctrl.connect()
            self.sel.register(self.ctrl.sock, sel.EVENT_READ)
        except HTTPException as httpe:
            logging.error("Failed to connect to server.")
            logging.error(httpe)
        else:
            return True
        if retry:
            logging.info("Retrying connection to server.")
            return self.connect(False)
        else:
            logging.error("Server unreachable. Exiting.")
            return False

    def __successful(self, error: str, ceiling: int) -> bool:
        if self.response.status >= 200 and self.response.status < ceiling:
            return True
        else:
            logging.error("Bad response from server.")
            logging.error(f"Failed to {error}: ")
            logging.error(f'\tFailure Code: {self.response.status}')
            logging.error(f'\tFailure Reason: {self.response.reason}')
            return False

    def __getresponse(self, timeout=5) -> bool:
        try:
            self.sel.modify(self.ctrl.sock, sel.EVENT_READ)
            if self.sel.select(timeout=timeout):
                self.response = self.ctrl.getresponse()
                length = self.response.length
                self.response_data = self.response.read(length)
                return True
        except TimeoutError:
            logging.error("Timed-out waiting for response.")
            return False
        except KeyboardInterrupt:
            return False

    def __submit_registration(self, retry=True) -> bool:
        registration = json.dumps({"MAC": self.mac})
        try:
            uri = "/controller/register"
            headers = {"Content-Type": "application/json"}
            self.ctrl.request("POST", uri, registration, headers)
        except HTTPException as httpe:
            logging.error("Registration request failed to send.")
            logging.error(httpe)
            if retry:
                logging.info("Retrying.")
                return self.__submit_registration(False)
            return False
        else:
            return self.__getresponse()

    def register(self, retry=True) -> bool:
        logging.info(f'MAC Address detected: {self.mac}.')
        logging.info(f'Registering with server.')
        if not self.__submit_registration():
            return False
        elif self.__successful("register with server", 400):
            return True
        elif retry:
            logging.info("Retrying.")
            return self.register(False)
        else:
            return False

    def __deserialize_device_list(self, data: bytes) -> list:
        try:
            logging.info("Deserializing device list.")
            devices = json.loads(data)
            logging.info("Validating device list against request schema.")
            if len(devices) > 0:
                self.request_schema.validate(devices)
        except ValidationError as ve:
            logging.error("Device list failed validation.")
            logging.error(ve)
        except json.decoder.JSONDecodeError as jde:
            logging.error("Device list could not be deserialized.")
            logging.error(jde)
        else:
            return devices
        return []

    def get_devices(self) -> list:
        msg = "request available devices from the server"
        try:
            logging.info(f"Requesting {msg[7:]}.")
            self.ctrl.request("GET", "/sssf")
        except HTTPException as httpe:
            logging.error(f"Failed to {msg}.")
            logging.error(httpe)
        else:
            if self.__getresponse() and self.__successful(msg, 400):
                return self.__deserialize_device_list(self.response_data)

    def request_devices(self, _req: list, _devices: list) -> bool:
        msg = "request desired devices from the server"
        logging.info(f"Requesting {msg[7:]}")
        req = [i for i in _devices if i["ID"] in _req]
        requestJSON = json.dumps({"MAC": self.mac, "Devices": req})
        try:
            uri = "/controller/session"
            headers = {"Content-Type": "application/json"}
            self.ctrl.request("POST", uri, requestJSON, headers)
        except HTTPException as httpe:
            logging.error(f"Failed to {msg}.")
            logging.error(httpe)
            return False
        else:
            return self.__getresponse() and self.__successful(msg, 300)

    def receive_SSE(self, key: sel.SelectorKey):
        logging.debug("Received an SSE.")
        sleep(0.1)
        message = self.ctrl.sock.recv(4096)
        with BytesIO() as self.wfile, BytesIO(message) as self.rfile:
            self.handle_one_request()
        if self.close_connection:
            logging.error("Server closed the connection.")
            self.stop_session()

    def do_POST(self):
        try:
            request_data = json.load(self.rfile)
            self.session_schema.validate(request_data)
            ip = IPv4Address(request_data["IP"])
            port = request_data["Port"]
            return ip, port, request_data
        except (ValidationError,
                JSONDecodeError,
                AddressValueError) as ve:
            logging.error(ve)
            self.close_connection = True
            return None

    def __send_delete(self, path: str):
        logging.info(f'Sending DELETE.')
        try:
            headers = {"Connection": "keep-alive"}
            self.ctrl.request("DELETE", path, headers=headers)
            self.sel.modify(self.ctrl.sock, sel.EVENT_READ)
        except HTTPException as httpe:
            logging.error("-> Delete request failed to send.")
            logging.error(httpe)
        else:
            self.__getresponse()

    def do_DELETE(self):
        self.__send_delete("/controller/session")

    def shutdown(self, notify_server=True):
        logging.debug("Shutting down server connection.")
        if notify_server:
            if not self.close_connection:
                self.__send_delete("/controller/register")
            else:
                logging.warning(
                    "Cannot unregister with server because "
                    "server already closed the connection."
                    )
        self.sel.unregister(self.ctrl.sock)
        self.ctrl.sock.shutdown(soc.SHUT_RDWR)
        self.ctrl.sock.close()
