import socket
import json
import jsonschema
import http.client
import selectors
import logging
import os
from ipaddress import IPv4Address, AddressValueError
from io import BytesIO
from http.server import BaseHTTPRequestHandler
from logging.handlers import TimedRotatingFileHandler
from HelperMethods import ColoredConsoleHandler, Schema
from getmac import get_mac_address as gma

class BrokerHandle(BaseHTTPRequestHandler):
    def __init__(self, _sel: selectors.DefaultSelector, _server_address = socket.gethostname()) -> None:
        self.__setup_logging()
        self.mac = gma()
        self.sel = _sel
        self.server_address = _server_address
        self.protocol_version = "HTTP/1.1"
        self.close_connection = False
        self.request_schema = Schema.compile_schema("RequestECUs.json")
        self.session_schema = Schema.compile_schema("SessionInformation.json")
        self.mcast_IP = IPv4Address()
        self.can_port = 0
        self.carla_port = 0
        # self.mac = "00:0C:29:DE:AD:BE"

    # Overrides for the parent functions

    def log_error(self, format, *args):
        logging.error("%s - - %s\n" %
                         ("SERVER", format%args))

    def log_message(self, format, *args):
        logging.info("%s - - %s\n" %
                         ("SERVER", format%args))
    
    # ----------------------------------

    def __setup_logging(self) -> None:
        logging.basicConfig(
            format='%(asctime)s - %(filename)s - %(levelname)s - %(message)s',
            level=logging.DEBUG,
            handlers=[
                TimedRotatingFileHandler(
                    filename="sss3_log",
                    when="midnight",
                    interval=1,
                    backupCount=7,
                    encoding='utf-8'
                    ),
                ColoredConsoleHandler()
                ]
            )
        # self.logger = logging.getLogger(__name__)
        # self.logger.setLevel(logging.DEBUG)
    
    def connect(self, retry = True) -> bool:
        try:
            self.ctrl = http.client.HTTPConnection(self._server_address)
        except http.client.HTTPException as httpe:
            logging.error("Unable to connect to server.")
            self.__handle_connection_errors(httpe)
        else:
            logging.info("Successfully connected to server")
            self.__set_keepalive(self.ctrl.sock, 300000, 300000)
            return True
        if retry:
            logging.info("Retrying connection to server.")
            return self.connect(False)
        else:
            logging.error("Server unreachable. Exiting.")
            return False
    
    def __set_keepalive(self, conn: socket.socket, idle_sec: int, interval_sec: int) -> None:
        logging.info(f'Setting Keep-Alive idle seconds to {idle_sec}.')
        logging.info(f'Setting Keep-Alive interval seconds to {interval_sec}.')
        if os.name == 'nt':
            conn.ioctl(socket.SIO_KEEPALIVE_VALS, (1, idle_sec, interval_sec))
        else:
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle_sec)
            conn.setsockopt(socket.IPPROTO_TCP,
                            socket.TCP_KEEPINTVL, interval_sec)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 10)

    def __wait_for_socket(self, timeout=None) -> bool:
        try:
            if self.sel.select(timeout=timeout):
                return True
        except TimeoutError:
            logging.error("Selector timed-out while waiting for a response or SSE.")
            return False
        except KeyboardInterrupt:
            return False
    
    def __submit_registration(self, registration: str) -> http.client.HTTPResponse:
        logging.info("-> Sending registration request.")
        try:
            self.ctrl.request("POST", "/client/register", registration)
            logging.info("-> Registration request successfully sent!")
            self.sel.register(self.ctrl.sock, selectors.EVENT_READ)
        except http.client.HTTPException as httpe:
            logging.error("-> Registration request failed to send.")
            self.__handle_connection_errors(httpe)
        else:
            if self.__wait_for_socket():
                return self.ctrl.getresponse()

    def register(self) -> bool:
        logging.info(f'Attempting to register with server using this MAC address: {self.mac}.')
        self.response = self.__submit_registration(json.dumps({"MAC": self.mac}))
        self.response_data = self.response.read(self.response.length)
        if self.response.status >= 200 and self.response.status < 300:
            logging.info("Successfully registered with the server.")
            return True
        else:
            logging.error("Failed to register with server: ")
            logging.error(f'\tFailure Code: {self.response.status}')
            logging.error(f'\tFailure Reason: {self.response.reason}')
            return False

    def __handle_connection_errors(self, error) -> None:
        if isinstance(error, http.client.NotConnected):
            logging.error("Not connected to server.")
            return
        if isinstance(error, http.client.RemoteDisconnected):
            logging.error("Server closed connection.")
            return
        elif isinstance(error, http.client.InvalidURL):
            logging.error("Invalid URL in request.")
            return
        elif isinstance(error, http.client.ImproperConnectionState):
            logging.error("Improper connection state with server.")
            return
        else:
            logging.error("Error occured within the HTTP connection.")

    def get_devices(self) -> list:
        try:
            logging.info("Requesting available devices from the server.")
            self.ctrl.request("GET", "/sss3")
        except http.client.HTTPException as httpe:
            self.__handle_connection_errors(httpe)
        else:
            if self.__wait_for_socket():
                self.response = self.ctrl.getresponse()
                self.response_data = self.response.read(self.response.length)
                return self.__validate_device_list_response(self.response, self.response_data)

    def __validate_device_list_response(self, response: http.client.HTTPResponse, data: bytes) -> list:
        if response.status >= 200 and response.status < 300:
            logging.info("Request for available devices was successful.")
            return self.__deserialize_device_list(data)
        else:
            logging.error("Request for available devices failed.")
            logging.error(f'\tFailure Code: {response.status}')
            logging.error(f'\tFailure Reason: {response.reason}')
            return []

    def __deserialize_device_list(self, data: bytes) -> list:
        try:
            logging.info("Deserializing device list.")
            available_devices = json.loads(data)
            logging.info("Validating device list against request schema.")
            self.request_schema.validate(available_devices)
            return available_devices
        except jsonschema.ValidationError:
            logging.error("Device list failed validation again request schema.")
            return []
        except json.decoder.JSONDecodeError:
            logging.error("Device list could not be deserialized.")
            return []

    def request_devices(self, devices: list) -> bool:
        requestJSON = json.dumps({"MAC": self.mac, "ECUs": devices})
        try:
            logging.info("Requesting devices from the server.")
            self.ctrl.request("POST", "/session", requestJSON)
        except http.client.HTTPException as httpe:
            self.__handle_connection_errors(httpe)
            return False
        else:
            if self.__wait_for_socket():
                self.response = self.ctrl.getresponse()
                self.response_data = self.response.read(self.response.length)
                return self.__validate_request_device_response(self.response)

    def __validate_request_device_response(self, response: http.client.HTTPResponse) -> bool:
        if response.status >= 200 and response.status < 300:
            logging.info("Request for selected devices was successful.")
            return True
        else:
            logging.error("Request for selected devices failed.")
            logging.error(f'\tFailure Code: {response.status}')
            logging.error(f'\tFailure Reason: {response.reason}')
            return False

    def receive_SSE(self, key: selectors.SelectorKey):
        logging.debug("Received an SSE.")
        self.__handle_SSE(self.ctrl.sock.recv(4096))
        if self.close_connection:
            logging.error("Server closed the connection.")
            self.__shutdown_connection(key)

    def __handle_SSE(self, message: bytes):
        with BytesIO() as self.wfile, BytesIO(message) as self.rfile:
            self.handle_one_request()

    def do_POST(self):
        logging.debug("SSE is a POST.")
        try:
            data = json.loads(self.rfile)
            self.session_schema.validate(data)
            self.mcast_IP = IPv4Address(data["IP"])
            self.can_port = data["CAN_PORT"]
            self.carla_port = data["CARLA_PORT"]
        except jsonschema.ValidationError as ve:
            logging.error(ve)
            self.close_connection = True
            raise SyntaxError from ve
        except json.decoder.JSONDecodeError as jde:
            logging.error(jde)
            self.close_connection = True
            raise SyntaxError from jde
        except AddressValueError as ave:
            logging.error(ave)
            self.close_connection = True
            raise SyntaxError from ave

    def do_DELETE(self):
        logging.debug("SSE is a DELETE.")
        logging.info("Server closed the current session.")
        self.mcast_IP = IPv4Address()
        self.can_port = 0
        self.carla_port = 0

    def send_delete(self, path: str, close = False):
        logging.info(f'Sending DELETE.')
        response = None
        try:
            self.ctrl.request("DELETE", path)
            self.sel.register(self.ctrl.sock, selectors.EVENT_READ)
        except http.client.HTTPException as httpe:
            logging.error("-> Delete request failed to send.")
            self.__handle_connection_errors(httpe)
        else:
            if self.__wait_for_socket():
                response = self.ctrl.getresponse()
        finally:
            if close:
                key = self.sel.get_key(self.ctrl.sock)
                self.shutdown_connection(key)
                self.do_DELETE()
            return response

    def shutdown_connection(self, key: selectors.SelectorKey):
        logging.debug("Unregistering the file object.")
        self.sel.unregister(key.fileobj)
        logging.debug("Shutting down the socket.")
        key.fileobj.shutdown(socket.SHUT_RDWR)
        logging.debug("Closing the socket object.")
        key.fileobj.close()