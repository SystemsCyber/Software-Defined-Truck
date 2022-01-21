import logging
import selectors as sel
import socket as soc
from ctypes import (Structure, Union, c_bool, c_int8, c_uint8, c_uint16,
                    c_uint32)
from enum import Enum, auto
from ipaddress import IPv4Address
from types import SimpleNamespace

import netifaces
from getmac import get_mac_address as gma

from Environment import LogSetup


class FLAGS_FD(Structure):
    _pack_ = 4
    _fields_ = [
        ("extended", c_bool),
        ("overrun", c_bool),
        ("reserved", c_bool)
    ]

    def __repr__(self) -> str:
        return (
            f'\textended: {self.extended} overrun: {self.overrun} reserved: {self.reserved}\n'
        )


class CANFD_message_t(Structure):
    _pack_ = 4
    _fields_ = [
        ("can_id", c_uint32),
        ("can_timestamp", c_uint16),
        ("idhit", c_uint8),
        ("brs", c_bool),
        ("esi", c_bool),
        ("edl", c_bool),
        ("flags", FLAGS_FD),
        ("len", c_uint8),
        ("buf", c_uint8 * 64),
        ("mb", c_int8),
        ("bus", c_uint8),
        ("seq", c_bool)
    ]

    def __repr__(self) -> str:
        return (
            f'\tcan_id: {self.can_id} can_timestamp: {self.can_timestamp} idhit: {self.idhit}\n'
            f'\tbrs: {self.brs} esi: {self.esi} edl: {self.edl}\n'
            f'{self.flags}'
            f'\tlen: {self.len} buf: {self.buf}\n'
            f'\tmb: {self.mb} bus: {self.bus} seq: {self.seq}\n'
        )


class FLAGS(Structure):
    _pack_ = 4
    _fields_ = [
        ("extended", c_bool),
        ("remote", c_bool),
        ("overrun", c_bool),
        ("reserved", c_bool)
    ]

    def __repr__(self) -> str:
        return (
            f'\textended: {self.extended} remote: {self.remote} overrun: {self.overrun} reserved: {self.reserved}\n'
        )


class CAN_message_t(Structure):
    _pack_ = 4
    _fields_ = [
        ("can_id", c_uint32),
        ("can_timestamp", c_uint16),
        ("idhit", c_uint8),
        ("flags", FLAGS),
        ("len", c_uint8),
        ("buf", c_uint8 * 8),
        ("mb", c_int8),
        ("bus", c_uint8),
        ("seq", c_bool)
    ]

    def __repr__(self) -> str:
        return (
            f'\tcan_id: {self.can_id} can_timestamp: {self.can_timestamp} idhit: {self.idhit}\n'
            f'{self.flags}'
            f'\tlen: {self.len} buf: {self.buf}\n'
            f'\tmb: {self.mb} bus: {self.bus} seq: {self.seq}\n'
        )


class WCANFrame(Union):
    _pack_ = 4
    _fields_ = [
        ("can", CAN_message_t),
        ("can_FD", CANFD_message_t)
    ]


class WCANBlock(Structure):
    _anonymous_ = ("frame",)
    _pack_ = 4
    _fields_ = [
        ("sequence_number", c_uint32),
        ("need_response", c_bool),
        ("fd", c_bool),
        ("frame", WCANFrame)
    ]

    def __repr__(self) -> str:
        s = (
            f'\tSequence Number: {self.sequence_number} '
            f'Need Response: {self.need_response} FD: {self.fd}\n'
        )
        if self.fd:
            s += f'\tFrame:\n{self.frame.can_FD}\n'
        else:
            s += f'\tFrame:\n{self.frame.can}\n'
        return s


class CANNode(object):
    class SessionStatus(Enum):
        Inactive = auto()
        Active = auto()

    def __init__(self, *args, **kwargs) -> None:
        LogSetup.init_logging()
        self.__can_ip = IPv4Address
        self.__can_port = 0
        self.sel = sel.DefaultSelector()

        self.mac = gma()
        self._sequence_number = 1
        self.session_status = self.SessionStatus.Inactive

        self.mac = "00:0C:29:DE:AD:BE"  # For testing purposes
        logging.debug(f"The testing MAC address is: {self.mac}")

    def __init_socket(self, can_port: int, mreq: bytes, iface: bytes):
        logging.info("Creating CANNode socket.")
        self.__can_sock = soc.socket(
            soc.AF_INET, soc.SOCK_DGRAM, soc.IPPROTO_UDP)
        self.__can_sock.setsockopt(soc.SOL_SOCKET, soc.SO_REUSEADDR, 1)
        self.__can_sock.setsockopt(
            soc.IPPROTO_IP, soc.IP_MULTICAST_LOOP, False)
        self.__can_sock.setsockopt(soc.IPPROTO_IP, soc.IP_MULTICAST_TTL, 128)
        self.__can_sock.setsockopt(soc.IPPROTO_IP, soc.IP_MULTICAST_IF, iface)
        self.__can_sock.setsockopt(soc.IPPROTO_IP, soc.IP_ADD_MEMBERSHIP, mreq)
        self.__can_sock.setblocking(False)
        self.__can_sock.bind(('', can_port))

    def __create_group_info(self, ip: IPv4Address) -> bytes:
        default_gw = netifaces.gateways()["default"][netifaces.AF_INET]
        gw = IPv4Address(default_gw[0])
        logging.info(f"Default IPv4 Gateway: {gw}")
        device_addresses = soc.gethostbyname_ex(soc.gethostname())[2]
        logging.info(f"Device interface addresses: {device_addresses}")
        closest_ip = str
        smallest_diff = 9999999999
        for i in netifaces.ifaddresses(default_gw[1])[netifaces.AF_INET]:
            _ip = IPv4Address(i["addr"])
            diff = abs(int(gw) - int(_ip))
            if (diff < smallest_diff) and (str(_ip) in device_addresses):
                smallest_diff = diff
                closest_ip = str(_ip)
        logging.info(f"Closest IP found to default gateway: {closest_ip}")
        logging.info("Multicast interface chosen: " + closest_ip)
        iface = soc.inet_aton(closest_ip)
        group = soc.inet_aton(str(ip))
        mreq = group + iface
        return iface, mreq

    def start_session(self, _ip: IPv4Address, _port: int) -> None:
        self.__can_ip = _ip
        self.__can_port = _port
        self.__iface, self.__mreq = self.__create_group_info(self.__can_ip)
        self.__init_socket(self.__can_port, self.__mreq, self.__iface)
        can_data = SimpleNamespace(callback=self.read, message=None)
        self.can_key = self.sel.register(
            self.__can_sock, sel.EVENT_READ, can_data)
        self.session_status = self.SessionStatus.Active

    def read(self) -> bytes:
        try:
            return self.__can_sock.recv(1024)
        except OSError as oe:
            logging.debug("Occured in read")
            logging.error(oe)

    def packCAN(self, can_frame: CAN_message_t) -> WCANBlock:
        message = WCANBlock(
            self._sequence_number,
            False,
            False,
            WCANFrame(can_frame)
        )
        self._sequence_number += 1
        return message

    def packCANFD(self, can_frame: CANFD_message_t) -> WCANBlock:
        message = WCANBlock(
            self._sequence_number,
            False,
            True,
            WCANFrame(can_frame)
        )
        self._sequence_number += 1
        return message

    def write(self, message: bytes) -> int:
        try:
            return self.__can_sock.sendto(
                message,
                (str(self.__can_ip), self.__can_port)
            )
        except OSError as oe:
            logging.error(oe)

    def stop_session(self) -> None:
        self.__can_ip = IPv4Address
        self.__can_port = 0
        if self.session_status == self.SessionStatus.Active:
            logging.info("Shutting down CAN socket.")
            self.sel.unregister(self.__can_sock)
            self.__can_sock.setsockopt(
                soc.IPPROTO_IP, soc.IP_DROP_MEMBERSHIP, self.__mreq)
            self.__can_sock.shutdown(soc.SHUT_RDWR)
            self.__can_sock.close()
            self.session_status = self.SessionStatus.Inactive
