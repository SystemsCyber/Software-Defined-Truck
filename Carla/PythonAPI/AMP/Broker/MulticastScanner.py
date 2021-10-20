import threading
import socket as sckt
import struct
import ipaddress
from typing import List, Tuple, Dict
# TODO add method to safely close the thread and release the sockets

class MulticastScanner:
    """This library is used to scan a given address range and ports for IP
       address with little to no activity on them.
    """

    def __init__(self, network_address: ipaddress.IPv4Network, ports: List[int]) -> None:
        """Creates a new thread that contiues to scan the given IP address range in the background.

        Parameters
        ==========
            network_address: The network address and prefix length in the form of an ipaddress object.
            ports: The list of ports to scan.

        Returns
        =======
            Nothing. The list of free IP address can be obtain through the thread safe getters and setters in this class.
        """
        self.network_address = network_address
        self.ports = ports
        self.lock = threading.Lock()
        self.run = True
        self.__ip_addresses = []
        for ip in self.network_address.hosts():
            self.__ip_addresses.append({
                "ip": ip,
                "available": False,
                "sockets": self.__initialize_sockets(ip, ports)
            })
        self.scanner = threading.Thread(target=self.__scan_network)

    def __initialize_sockets(ip: ipaddress.IPv4Address, ports: List[int]) -> List[sckt.socket]:
        lsocks = []
        for port in ports:
            lsock = sckt.socket(
                sckt.AF_INET, sckt.SOCK_DGRAM, sckt.IPPROTO_UDP)
            lsock.setsockopt(sckt.SOL_SOCKET, sckt.SO_REUSEADDR, 2)
            lsock.bind((ip, port))
            mreq = struct.pack("4sl", sckt.inet_aton(ip), sckt.INADDR_ANY)
            lsock.setsockopt(sckt.IPPROTO_IP, sckt.IP_ADD_MEMBERSHIP, mreq)
            lsock.settimeout(1)
            lsocks.append(lsock)
        return lsocks

    def __scan_network(self) -> None:
        while self.run:
            for ip in self.__ip_addresses:
                with self.lock:
                    ip["available"] = self.__check_address(ip["sockets"])
        self.__shutdown()

    def __check_address(sockets: List[sckt.socket]) -> bool:
        for sock in sockets:
            try:
                sock.recv(1)
                sock.shutdown(sckt.SHUT_RDWR)
                sock.close()
                return False
            except sckt.timeout:  # Timing out means mcast addr is free
                continue
        return True  # Times out for all addresses in dictionary

    def __shutdown(self) -> None:
        with self.lock:
            for ip in self.__ip_addresses:
                    for sock in ip["sockets"]:
                        sock.shutdown(sckt.SHUT_RDWR)
                        sock.close()

    def get_ip_status(self, _ip: ipaddress.IPv4Address):
        with self.lock:
            for ip in self.__ip_addresses:
                if ip["ip"] == _ip:
                    return ip["available"]

    def get_free_ip(self):
        with self.lock:
            for ip in self.__ip_addresses:
                if ip["available"]:
                    return ip["ip"]
