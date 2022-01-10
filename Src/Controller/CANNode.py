import ipaddress
import netifaces
import logging
import copy
from os import path, walk, getcwd
from logging.handlers import TimedRotatingFileHandler
from ipaddress import IPv4Address
from enum import Enum, auto
from getmac import get_mac_address as gma
from threading import Lock
from types import SimpleNamespace
from socket import *
from selectors import *
from ctypes import *

# COPIED FROM: https://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output?page=1&tab=votes#tab-top
class ColoredConsoleHandler(logging.StreamHandler):
    def emit(self, record):
        # Need to make a actual copy of the record
        # to prevent altering the message for other loggers
        myrecord = copy.copy(record)
        levelno = myrecord.levelno
        if(levelno >= 50):  # CRITICAL / FATAL
            color = '\x1b[31m'  # red
        elif(levelno >= 40):  # ERROR
            color = '\x1b[31m'  # red
        elif(levelno >= 30):  # WARNING
            color = '\x1b[33m'  # yellow
        elif(levelno >= 20):  # INFO
            color = '\x1b[32m'  # green
        elif(levelno >= 10):  # DEBUG
            color = '\x1b[35m'  # pink
        else:  # NOTSET and anything else
            color = '\x1b[0m'  # normal
        myrecord.levelname = color + str(myrecord.levelname) + '\x1b[0m'  # normal
        logging.StreamHandler.emit(self, myrecord)
# ------------------------------------------------------------

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
            f'\tcan_id: {self.can_id} can_timestamp: {self.can_timestamp} idhit: {self.id_hit}\n'
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
            f'Sequence Number: {self.sequence_number}\n'
            f'Need Response: {self.need_response} FD: {self.fd}\n'
        )
        if self.fd:
            s += f'Frame:\n{self.frame.can}\n'
        else:
            s += f'Frame:\n{self.frame.can_FD}\n'
        return s

class CANNode:
    class SessionStatus(Enum):
        Inactive = auto()
        Active = auto()

    def __init__(self) -> None:
        self.__init_logging()
        self.__can_ip = IPv4Address
        self.__can_port = 0

        self.sel = DefaultSelector()
        self.sel_lock = Lock()

        self.mac = gma()
        self.sequence_number = 1
        self.session_status = self.SessionStatus.Inactive

        self.mac = "00:0C:29:DE:AD:BE"  # For testing purposes
        logging.debug(f"The testing MAC address is: {self.mac}")

    def __findpath(self, log_name):
        base_dir = path.abspath(getcwd())
        for root, dirs, files in walk(base_dir):
            for name in dirs:
                if name == "Logs":
                    log_path = path.join(root, name)
                    return path.join(log_path, log_name)
        log_path = path.join(base_dir, "Logs")
        return path.join(log_path, log_name)
    
    def __init_logging(self) -> None:
        filename = self.__findpath("controller_log")
        logging.basicConfig(
            format='%(asctime)-15s %(module)-10.10s %(levelname)s %(message)s',
            level=logging.DEBUG,
            handlers=[
                TimedRotatingFileHandler(
                    filename=filename,
                    when="midnight",
                    interval=1,
                    backupCount=7,
                    encoding='utf-8'
                    ),
                ColoredConsoleHandler()
                ]
            )
    
    def __init_socket(self, can_port: int, mreq: bytes, iface: bytes):
        logging.info("Creating CANNode socket.")
        self.__can_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        self.__can_sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.__can_sock.setsockopt(IPPROTO_IP, IP_MULTICAST_LOOP, False)
        self.__can_sock.setsockopt(IPPROTO_IP, IP_MULTICAST_TTL, 128)
        self.__can_sock.setsockopt(IPPROTO_IP, IP_MULTICAST_IF, iface)
        self.__can_sock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq)
        self.__can_sock.setblocking(False)
        self.__can_sock.bind(('', can_port))
    
    def __create_group_info(self, ip: IPv4Address) -> bytes:
        default_gw = netifaces.gateways()["default"][netifaces.AF_INET]
        gw = IPv4Address(default_gw[0])
        logging.info(f"Default IPv4 Gateway: {gw}")
        device_addresses = gethostbyname_ex(gethostname())[2]
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
        iface = inet_aton(closest_ip)
        group = inet_aton(str(ip))
        mreq = group + iface
        return iface, mreq

    def start_session(self, _ip: IPv4Address, _port: int) -> None:
        self.__can_ip = _ip
        self.__can_port = _port
        self.__iface, self.__mreq = self.__create_group_info(self.__can_ip)
        self.__init_socket(self.__can_port, self.__mreq, self.__iface)
        can_data = SimpleNamespace(callback = self.read, message = None)
        with self.sel_lock:
            self.can_key = self.sel.register(self.__can_sock, EVENT_READ, can_data)
        self.session_status = self.SessionStatus.Active

    def read(self) -> bytes:
        try:
            return self.__can_sock.recv(1024)
        except OSError as oe:
            logging.debug("Occured in read")
            logging.error(oe)

    def packCAN(self, can_frame: CAN_message_t) -> WCANBlock:
        message = WCANBlock(
            self.sequence_number,
            False,
            False,
            WCANFrame(can_frame)
            )
        self.sequence_number += 1
        return message

    def packCANFD(self, can_frame: CANFD_message_t) -> WCANBlock:
        message = WCANBlock(
            self.sequence_number,
            False,
            True,
            WCANFrame(can_frame)
            )
        self.sequence_number += 1
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
            with self.sel_lock:
                self.sel.unregister(self.__can_sock)
            self.__can_sock.setsockopt(IPPROTO_IP, IP_DROP_MEMBERSHIP, self.__mreq)
            self.__can_sock.shutdown(SHUT_RDWR)
            self.__can_sock.close()
            self.session_status = self.SessionStatus.Inactive