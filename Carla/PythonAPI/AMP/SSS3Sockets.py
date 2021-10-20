import logging
from socket import *
from ipaddress import IPv4Address

class SSS3Sockets:

    def __init__(self, _mcast_IP: IPv4Address, _can_port: int, _carla_port: int) -> None:
        self.mcast_IP = _mcast_IP
        self.can_port = _can_port
        self.carla_port = _carla_port
        self.iface, self.mreq = self.__create_mcast_info(self.mcast_IP)
        self.can = self.__create_can_socket(self.can_port, self.mreq)
        self.carla = self.__create_carla_socket(self.iface)

    def __create_mcast_info(self, ip: IPv4Address) -> bytes:
        device_address = gethostbyname_ex(gethostname())[2][3]
        logging.info(device_address + " was chosen as the interface to subscribe to for multicast messages.")
        iface = inet_aton(device_address)
        group = inet_aton(str(ip))
        mreq = group + iface
        return iface, mreq

    def __create_can_socket(self, can_port: int, mreq: bytes) -> socket:
        logging.info("Creating CAN socket.")
        can = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        can.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        can.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq)
        can.bind(('', can_port))
        can.setblocking(False)
        return can

    def __create_carla_socket(self, iface: bytes) -> socket:
        logging.info("Creating CARLA socket.")
        carla = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        carla.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        carla.setsockopt(IPPROTO_IP, IP_MULTICAST_TTL, 128)
        carla.setsockopt(IPPROTO_IP, IP_MULTICAST_IF, iface)
        carla.setblocking(False)
        return carla

    def stop(self) -> None:
        self.mcast_IP = IPv4Address
        self.can_port = 0
        self.carla_port = 0
        logging.info("Shutting down CAN socket.")
        self.can.setsockopt(IPPROTO_IP, IP_DROP_MEMBERSHIP, self.mreq)
        self.can.shutdown(SHUT_RDWR)
        self.can.close()
        logging.info("Shutting down carla socket.")
        self.carla.shutdown(SHUT_RDWR)
        self.carla.close()

    def send_carla_frame(self, message: bytes) -> None:
        self.carla.sendto(message, (str(self.mcast_IP), self.carla_port))

    def receive_can_messages(self) -> bytes:
        return self.can.recv(36)