import logging
import struct
from Node import Node
from ipaddress import IPv4Address
from Frame import CAN_UDP_Frame as CANFrame
from socket import *

class CANNode(Node):
    def __init__(self) -> None:
        self.id = None
        self.last_transmission_time = None
        self.can_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        super(CANNode, self).__init__()
    
    def __init_socket(self, can_port: int, mreq: bytes, iface: bytes):
        logging.info("Creating CANNode socket.")
        self.can_sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.can_sock.setsockopt(IPPROTO_IP, IP_MULTICAST_TTL, 128)
        self.can_sock.setsockopt(IPPROTO_IP, IP_MULTICAST_IF, iface)
        self.can_sock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq)
        self.can_sock.setblocking(False)
        self.can_sock.bind(('', can_port))
    
    def __create_group_info(self, ip: IPv4Address) -> bytes:
        device_address = gethostbyname_ex(gethostname())[2][3]
        logging.info(device_address + " was chosen as the interface to subscribe to for multicast messages.")
        iface = inet_aton(device_address)
        group = inet_aton(str(ip))
        mreq = group + iface
        return iface, mreq

    def start_session(self) -> None:
        self.iface, self.mreq = self.__create_group_info(self.can_ip)
        self.__init_socket(self.can_port, self.mreq, self.iface)

    def __unpack(self, buffer) -> CANFrame:
        return CANFrame(struct.unpack("IIIIHB????Bs8bB?x", buffer))

    def read(self) -> CANFrame:
        return self.__unpack(self.can_sock.recv(36))

    def write(self, message: bytes) -> None:
        self.can_sock.sendto(message, (str(self.can_ip), self.can_port))

    def stop_session(self) -> None:
        self.can_ip = IPv4Address
        self.can_port = 0
        logging.info("Shutting down CAN socket.")
        self.can_sock.setsockopt(IPPROTO_IP, IP_DROP_MEMBERSHIP, self.mreq)
        self.can_sock.shutdown(SHUT_RDWR)
        self.can_sock.close()