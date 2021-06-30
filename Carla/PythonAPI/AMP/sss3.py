import socket
import struct
import sys
import time
import subprocess
import os
import re
from typing import Union, Tuple, List, Dict, Optional
from frame import Frame

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
    """SSS3 communication utility in conjunction with the CARLA simulator

    Multicast allocation notes: 
        The multicast address range assigned for "Organization IPv4 Local Scope
        use" is 239.255.0.0/16. As such we must stay in this range.
        Unfortunately we still may run into conflicts, so upon creation of the
        SSS3 object it will allocate two multicast address and ports that are to
        the best of its ability, considered free to use.
    """

    def __init__(self, _address: ADDR_LIST, _mcast_address: Optional[str] = None) -> RETURN_ADDR_T:
        """
        Parameters
        ----------
        List of addresses (ip, port) of SSS3s.
        Optional - Multicast address for SSS3s to use.

        Returns
        -------
        The list of addresses of SSS3s that were setup correctly. If no SSS3s
        were setup correctly then an empty list is returned.
        """
        self.address = _address
        self.carla_port = 41664
        self.can_port = 41665
        self.frame = Frame()
        self.dropped_messages = 0
        self.timeouts = 0
        self.seq_miss_match = 0
        if _mcast_address:
            self.mcast_ip = _mcast_address
            sock_pair = socket.socketpair(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.socks = {"carla": sock_pair[0], "can": sock_pair[1]}
            self.__set_mcast_options(_mcast_address, self.socks)
        else:
            self.mcast_ip, self.socks = self.__allocate_mcast_addr()
        # TODO add functions to maintain hold on multicast address
        return self.__setup_sss3(_address)

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

    def __allocate_mcast_addr(self) -> MCAST_SOCKS:
        try:
            return self.__test_mcast_addr_range()
        except OSError as err:
            print(f"OS error: {err}")
            raise
        except Exception as err:
            print(f"Error: {err}")
            raise

    def __test_mcast_addr_range(self) -> MCAST_SOCKS:
        for a in range(255, 0, -1):
            for b in range(255, 0, -1):
                mcast_grp = "239.255." + str(a) + "." + str(b)
                sock_pair = socket.socketpair(
                    socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock_dict = {"carla": sock_pair[0], "can": sock_pair[1]}
                self.__set_mcast_options(mcast_grp, sock_dict)
                if self.__check_mcast_address(sock_dict):
                    return mcast_grp, sock_dict
        raise Exception("No available multicast address could be found.")

    def __set_mcast_options(self, mcast_grp, socks: SOCK_DICT) -> None:
        for key, sock in socks.items():
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 2)
            sock.bind((mcast_grp, self[key + "_port"]))
            mreq = struct.pack("4sl", socket.inet_aton(mcast_grp),
                               socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP,
                            socket.IP_ADD_MEMBERSHIP, mreq)
            sock.settimeout(0.4)

    def __check_mcast_address(self, socks: SOCK_DICT) -> bool:
        for sock in socks.values():
            try:
                sock.recv(1)
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
                return False
            except socket.timeout:  # Timing out means mcast addr is free
                continue
        return True  # Times out for all addresses in dictionary

    def __setup_sss3(self, _address: ADDR_LIST) -> RETURN_ADDR_T:
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
