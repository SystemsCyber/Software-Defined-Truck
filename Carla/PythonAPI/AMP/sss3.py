import socket
import struct
import sys
import time
import subprocess
import os
import re
from typing import Union, Tuple, List, Dict, Optional
from frame import Frame
import selectors
from types import SimpleNamespace
from getmac import get_mac_address as gma
import json
import http.client

# Type Aliases
SOCK_T = socket.socket
if sys.version_info >= (3, 9):
    SOCK_DICT = dict[str, SOCK_T]
    MCAST_SOCKS = tuple[str, SOCK_DICT]
    ADDR_T = tuple[str, int]
    ADDR_LIST = list[ADDR_T]
    RETURN_ADDR_LIST = list[Union[ADDR_T, None]]
else:
    SOCK_DICT = Dict[str, SOCK_T]
    MCAST_SOCKS = Tuple[str, SOCK_DICT]
    ADDR_T = Tuple[str, int]
    ADDR_LIST = List[ADDR_T]
    RETURN_ADDR_T = List[Union[ADDR_T, None]]


class SSS3:
    """SSS3 communication utility in conjunction with the CARLA simulator"""

    def __init__(self, _server_address = socket.gethostname()) -> None:
        self.carla_port = 41664
        self.can_port = 41665
        self.frame = Frame()
        self.dropped_messages = 0
        self.timeouts = 0
        self.seq_miss_match = 0
        self.sel = selectors.DefaultSelector()
        if self.__connect_to_server(_server_address):
            self.__set_keepalive(self.ctrl.sock, 300000, 300000)
            self.sel.register(self.ctrl.sock, selectors.EVENT_READ)
            # self.__register(gma())
            self.__register("00:0C:29:DE:AD:BE")

    def __connect_to_server(self, _server_address: str):
        try:
            self.ctrl = http.client.HTTPConnection(_server_address)
        except http.client.GATEWAY_TIMEOUT:
            print("something about gateway timeout")
            return self.__retry_connect_to_server(_server_address)
        except http.client.REQUEST_TIMEOUT:
            print("Something about request timeout")
            return self.__retry_connect_to_server(_server_address)
        else:
            print("Something about successfully connecting to server")
            return True

    def __retry_connect_to_server(self, _server_address: str):
        print("Something about retrying connection to server")
        try:
            self.ctrl = http.client.HTTPConnection(_server_address)
        except http.client.GATEWAY_TIMEOUT:
            print("something about gateway timeout")
            print("something about server being unreachable")
            return False
        except http.client.REQUEST_TIMEOUT:
            print("Something about request timeout")
            print("Something about server being unreachable")
            return False
        else:
            print("Something about successfully connecting to server")
            return True
    
    def __set_keepalive(self, conn: socket.socket, idle_sec: int, interval_sec: int) -> None:
        if os.name == 'nt':
            conn.ioctl(socket.SIO_KEEPALIVE_VALS, (1, idle_sec, interval_sec))
        else:
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle_sec)
            conn.setsockopt(socket.IPPROTO_TCP,
                            socket.TCP_KEEPINTVL, interval_sec)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 10)

    def __wait_for_socket(self, timeout=None):
        try:
            if self.sel.select(timeout=timeout):
                return True
        except TimeoutError:
            print("Log something about server being disconnected")
            return False
        except KeyboardInterrupt:
            return False
    
    def __send_registration(self, registration: str) -> http.client.HTTPResponse:
        try:
            self.ctrl.request("POST", "/client/register", registration)
            self.sel.modify(self.ctrl.sock, selectors.EVENT_READ)
        except http.client.HTTPException as httpe:
            self.__handle_connection_errors(httpe)
        else:
            if self.__wait_for_socket():
                return self.ctrl.getresponse()

    def __register(self, mac: str) -> None:
        registration = json.dumps({"MAC": mac})
        print("Something about sending registration")
        self.response = self.__send_registration(registration)
        if self.response.status == 202:
            print("something about being successfully registered")
        else:
            print("Something about unable to register or server rejected registration")
            print("The response code for why the registration was rejected.")

    def __handle_connection_errors(self, error):
        pass

    def get_available_devices(self):
        try:
            print("something about requesting available devices.")
            self.ctrl.request("GET", "/sss3")
        except http.client.HTTPException as httpe:
            self.__handle_connection_errors(httpe)
        else:
            if self.__wait_for_socket():
                self.response = self.ctrl.getresponse()
                return self.response

    def send(self, control) -> None:
        message = self.frame.pack(control)
        self.socks["carla"].sendto(message, (self.mcast_ip, self.carla_port))

    def receive(self, control, verbose=False) -> None:
        try:
            data = self.socks["can"].recv(20)
            if len(data) == 20:  # 20 is size of carla struct in bytes
                ecm_data = struct.unpack("Ifff???B", data)
                if not self.frame(ecm_data, control, verbose):
                    self.__frame_miss_match(ecm_data, verbose)
        except socket.timeout:
            self.socks["can"].settimeout(0.04)
            self.dropped_messages += 1
            self.timeouts += 1
            print(f'Socket Timeout. Total: {self.timeouts}')

    def __frame_miss_match(self, ecm_data, verbose=False) -> None:
        self.dropped_messages += 1
        self.seq_miss_match += 1
        self.socks["can"].settimeout(0.01)
        for i in range(self.frame.last_frame - ecm_data[0]):
            self.socks["can"].recv(20)
            self.dropped_messages += 1
            self.seq_miss_match += 1
        self.socks["can"].settimeout(0.04)
        if verbose:
            print(ecm_data[0])
            print(self.frame.last_frame)
            print(
                f'Sequence number miss match. Total: {self.seq_miss_match}')

    def __set_mcast_options(self, mcast_grp, socks: SOCK_DICT) -> None:
        for key, sock in socks.items():
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
            sock.bind((mcast_grp, self[key + "_port"]))
            mreq = struct.pack("4sl", socket.inet_aton(mcast_grp),
                               socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP,
                            socket.IP_ADD_MEMBERSHIP, mreq)
            sock.settimeout(0.4)

    def __setup_sss3(self, _address: ADDR_LIST):
        source_addr = (self.__find_source_address(), _address[0][1])
        successfully_setup = []
        for address in _address:
            # Create Connection automatically tries all dns results for
            # hostname addresses on both IPv4 and IPv6.
            with socket.create_connection(address, 1, source_addr) as tcp_sock:
                tcp_sock.settimeout(1)
                if self.__send_setup(tcp_sock, address):
                    successfully_setup.append(address)
        return successfully_setup

    def __find_source_address(self) -> str:
        """
        If the host device is connected to multiple NICs then choose the one
        with the ip beginning in 192.168.X.X. If that IP does not exist then
        choose the first IP.
        """
        all_ip = re.compile(
            '([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})')
        local_subnet_ip = re.compile('192\.168\.([0-9]{1,3})\.([0-9]{1,3})')
        command = "ipconfig" if os.name == 'nt' else "ifconfig"
        all_ipconfig = all_ip.search(subprocess.check_output([command]))
        local_ipconfig = local_subnet_ip.search(
            subprocess.check_output([command]))
        if local_ipconfig:
            return local_ipconfig.group()
        else:
            return all_ipconfig.group()

    def __send_setup(self, tcp_sock: SOCK_T, address: ADDR_T, retry=True) -> bool:
        try:
            mcast_ip = socket.inet_aton(self.mcast_ip)
            mcast_packet_size = 20
            setup_message = struct.pack(
                "4sii", mcast_ip, self.carla_port, self.can_port, mcast_packet_size)
            tcp_sock.sendall(setup_message)
            confirmation = tcp_sock.recv(1)
            # True if sss3 setup correctly
            return struct.unpack("?", confirmation)[0]
        except (socket.herror, socket.gaierror, socket.timeout) as err:
            if retry:
                # DNS name assignment or socket closing may need to complete
                time.sleep(1)
                # Retry once
                return self.__send_setup(tcp_sock, address, False)
            else:
                print(f"Error: {err}")
                raise


if __name__ == '__main__':
    sss3object = SSS3()