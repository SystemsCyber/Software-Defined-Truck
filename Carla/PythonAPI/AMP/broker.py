import multiprocessing as mp
import socket
import struct
import time
import sys
import selectors
import queue
from types import SimpleNamespace
from collections.abc import Callable
from typing import Tuple, Dict, Union, List
from SSS3_Handle import SSS3Handle
from CARLA_Handle import CARLAHandle

# Type Aliases
LOCKTYPE = mp.Lock
SOCKTYPE = socket.socket
if sys.version_info >= (3, 9):
    MCAST_IP_ENTRY = (str, None | SOCKTYPE)
    MCAST_IPS = list[MCAST_IP_ENTRY]
    SSS3_ENTRY = selectors.SelectorKey
    SSS3S = list[SSS3_ENTRY]
    CARLA_CLIENT = selectors.SelectorKey
    CARLA_CLIENTS = list[CARLA_CLIENT]
    SAFE_LIST = MCAST_IPS | SSS3S | CARLA_CLIENTS
    SAFE_ENTRY = MCAST_IP_ENTRY | SSS3_ENTRY | CARLA_CLIENT
    SOCK_DICT = dict[str, SOCKTYPE]
    SAFE_INDEX = (int, int | str | None)
    CONN_HANDLE = (SOCKTYPE, (str, str))
else:
    MCAST_IP_ENTRY = Tuple[str, Union[None, SOCKTYPE]]
    MCAST_IPS = List[MCAST_IP_ENTRY]
    SSS3_ENTRY = selectors.SelectorKey
    SSS3S = List[SSS3_ENTRY]
    CARLA_CLIENT = selectors.SelectorKey
    CARLA_CLIENTS = List[CARLA_CLIENT]
    SAFE_LIST = Union[MCAST_IPS, SSS3S, CARLA_CLIENTS]
    SAFE_ENTRY = Union[MCAST_IP_ENTRY, SSS3_ENTRY, CARLA_CLIENT]
    SOCK_DICT = Dict[str, SOCKTYPE]
    SAFE_INDEX = Tuple[int, Union[int, str, None]]
    CONN_HANDLE = Tuple[SOCKTYPE, Tuple[str, str]]


class Broker:
    def __init__(self, _host_port=41660, _carla_port=41664, _can_port=41665) -> None:
        self.host_port = _host_port
        self.carla_port = _carla_port
        self.can_port = _can_port
        self.sss3_mac = bytes.fromhex("DEADBE")
        print("Broker Server Initializing...")
        print(f'\tHost Port: {self.host_port}')
        print(f'\tCarla Port: {self.carla_port}')
        print(f'\tCan Port: {self.can_port}')
        self.sel = selectors.DefaultSelector()
        self.multicast_IPs = []
        self.multicast_IP_lock = mp.Lock()
        self.SSS3s = []
        self.SSS3_lock = mp.Lock()
        self.carla_clients = []
        self.carla_client_lock = mp.Lock()
        self.free_mcast_address = False
        self.__init_mcast_ips()

    # ==================== Thread-Safe List Operations ====================

    def safe_add(safe_list: SAFE_LIST, lock: LOCKTYPE, entry: SAFE_ENTRY) -> None:
        with lock.acquire():
            safe_list.append(entry)

    def safe_remove(safe_list: SAFE_LIST, lock: LOCKTYPE, entry: SAFE_ENTRY) -> None:
        with lock.acquire():
            for i in range(len(safe_list)):
                if safe_list[i][0] == entry[0]:  # Only compare MACs
                    del safe_list[i]

    def safe_get(safe_list: SAFE_LIST, lock: LOCKTYPE, compare) -> SAFE_ENTRY:
        with lock.acquire():
            for i in range(len(safe_list)):
                if compare(i):
                    return i

    def safe_modify(safe_list: SAFE_LIST, lock: LOCKTYPE, safe_index: SAFE_INDEX, value) -> None:
        with lock.acquire():
            if safe_index[1]:
                safe_list[safe_index[0]] = value
            else:
                safe_list[safe_index[0]][safe_index[1]] = value

    # ==================== Multicast Address Opterations ====================

    def scanMulticastAddresses(self) -> None:
        for a in range(255, 0, -1):
            for b in range(255, 0, -1):
                mcast_grp = "239.255." + str(a) + "." + str(b)
                sock_pair = socket.socketpair(
                    socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock_dict = {"carla": sock_pair[0], "can": sock_pair[1]}
                self.__set_mcast_options(mcast_grp, sock_dict)
                free = self.__check_mcast_address(sock_dict)
                index = (((255 - a) * 255) + (255-b), 1)
                self.safe_modify(self.multicast_IPs,
                                 self.multicast_IP_lock, index, free)

    def __set_mcast_options(self, mcast_grp, socks: SOCK_DICT) -> None:
        for key, sock in socks.items():
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
            sock.bind((mcast_grp, self[key + "_port"]))
            mreq = struct.pack("4sl", socket.inet_aton(mcast_grp),
                               socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP,
                            socket.IP_ADD_MEMBERSHIP, mreq)
            sock.settimeout(1)  # Listen for 1 second.

    def __check_mcast_address(self, socks: SOCK_DICT) -> bool:
        for sock in socks.values():
            try:
                sock.recv(1)
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
                return False
            except socket.timeout:  # Timing out means mcast addr is free
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
        return True  # Times out for all addresses in dictionary

    def __init_mcast_ips(self) -> None:
        for a in range(255, 0, -1):
            for b in range(255, 0, -1):
                self.multicast_IPs.append(
                    ("239.255." + str(a) + "." + str(b), False, None))

    # ==================== Server / Broker Opterations ====================

    def listen(self):
        listening_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listening_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listening_socket.bind((socket.gethostname(), self.host_port))
        listening_socket.listen()
        listening_socket.setblocking(False)
        self.sel.register(listening_socket, selectors.EVENT_READ, data=None)
        print(f'Listening on: {socket.gethostname()}:{self.host_port}')
        # process = mp.Process(target=self.__wait_for_connection, args=(
        #                      listening_socket,), daemon=True)
        # process.start()
        self.__wait_for_connection()

    def __wait_for_connection(self) -> None:
        while True:
            # with self.SSS3_lock.acquire() as sl, self.carla_client_lock.acquire() as cl:
            connection_events = self.sel.select(timeout=1)
            for key, mask in connection_events:
                if mask & selectors.EVENT_READ:
                    self.__handle_read_events(key)
                elif mask & selectors.EVENT_WRITE:
                    self.__handle_write_events(key)
            self.__check_heartbeats(self.SSS3s)
            self.__check_heartbeats(self.carla_clients)

    def __handle_read_events(self, key: selectors.SelectorKey) -> None:
        # No data associated with the connection so it's new.
        if key.data is None:
            self.__accept_connection(key.fileobj)
        elif not hasattr(key.data, 'mac'):
            self.__register_device(key)
        elif key.data.type == "SSS3":
            print(f'Received Heartbeat from: {key.data.mac}.')
            key.data.heartbeat = time.time()
        elif (key.data.type == "CARLA Client") and (key.data.start):
            key.data.send_device_list(self.SSS3s)

    def __handle_write_events(self, key: selectors.SelectorKey) -> None:
        pass

    def __accept_connection(self, listening_socket: SOCKTYPE) -> None:
        conn, addr = listening_socket.accept()
        conn.setblocking(False)
        print(f'New connection from: {addr[0]}:{str(addr[1])}')
        self.sel.register(conn, selectors.EVENT_READ, data=addr)

    def __register_device(self, key: selectors.SelectorKey) -> None:
        mac = self.__getData(key.fileobj, key.data, 6)
        if not mac:
            return
        if mac[0:3] == self.sss3_mac:
            device = self.__getData(key.fileobj, key.data, 32)
            if device:
                newData = SSS3Handle(key.data, device, mac)
                newkey = self.sel.modify(key.fileobj, selectors.EVENT_READ, data=newData)
                self.SSS3s.append(newkey)
                self.__print_registration(newkey)
        elif mac[0:3] != self.sss3_mac:
            start = self.__getData(key.fileobj, key.data, 1)
            if start:
                newData = CARLAHandle(key.data, start, mac)
                newkey = self.sel.modify(key.fileobj, selectors.EVENT_WRITE, data=newData)
                self.carla_clients.append(newkey)
                self.__print_registration(newkey)

    def __getData(self, sock: SOCKTYPE, addr, num_bytes: int) -> Union[bytes, None]:
        raw_data = sock.recv(num_bytes)
        if (not raw_data) or (len(raw_data) < num_bytes):
            print(
                f'TCP closing command received from {addr[0]}. Closing connection...')
            self.sel.unregister(sock)
            sock.close()
            return None
        else:
            return raw_data

    def __print_registration(self, key: selectors.SelectorKey) -> None:
        print(f'New {key.data.type} connected:')
        print(f'\tIP: {key.data.addr}')
        print(f'\tPort: {key.data.port}')
        print(f'\tMAC: {key.data.mac}')
        if key.data.type == "SSS3":
            print("Attached Device: ")
            print(f'\tType: {key.data.attached_device["type"]}')
            print(f'\tYear: {key.data.attached_device["year"]}')
            print(f'\tMake: {key.data.attached_device["make"]}')
            print(f'\tModel: {key.data.attached_device["model"]}')

    def __check_heartbeats(self, connection_list: List):
        for conn in connection_list:
            # 300 seconds is 5 minutes
            if (time.time() - conn.data.heartbeat) > 300.0:
                print(f'Havent heard from {str(conn.data.mac)}', end='')
                print(f'({conn.data.type}) in 5 minutes. Device is ', end='')
                print("either down or abruptly disconnected.")
                print("Closing the connection and unregistering the device...")
                self.sel.unregister(conn.fileobj)
                conn.fileobj.close()

        # def setup_sss3(self, _address: List[str]) -> List[str]:
        #     successfully_setup = []
        #     for address in _address:
        #         # Create Connection automatically tries all dns results for
        #         # hostname addresses on both IPv4 and IPv6.
        #         with socket.create_connection(address, 1) as tcp_sock:
        #             tcp_sock.settimeout(1)
        #             if self.__send_setup(tcp_sock, address):
        #                 successfully_setup.append(address)
        #     return successfully_setup

        # def __send_setup(self, tcp_sock: SOCKTYPE, address: ADDR_T, retry=True) -> bool:
        #     try:
        #         mcast_ip = socket.inet_aton(self.mcast_ip)
        #         mcast_packet_size = 20
        #         setup_message = struct.pack(
        #             "4sii", mcast_ip, self.carla_port, self.can_port, mcast_packet_size)
        #         tcp_sock.sendall(setup_message)
        #         confirmation = tcp_sock.recv(1)
        #         # True if sss3 setup correctly
        #         return struct.unpack("?", confirmation)[0]
        #     except (socket.herror, socket.gaierror, socket.timeout) as err:
        #         if retry:
        #             # DNS name assignment or socket closing may need to complete
        #             time.sleep(1)
        #             # Retry once
        #             return self.__send_setup(tcp_sock, address, False)
        #         else:
        #             print(f"Error: {err}")
        #             raise
