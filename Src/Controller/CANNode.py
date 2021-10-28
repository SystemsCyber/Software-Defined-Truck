import logging
import struct
import copy
from os import path, walk, getcwd
from logging.handlers import TimedRotatingFileHandler
from ipaddress import IPv4Address
from Frame import CAN_UDP_Frame as CANFrame
from getmac import get_mac_address as gma
from socket import *

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

class CANNode:
    def __init__(self) -> None:
        self.__init_logging()
        self.id = None
        self.mac = gma()
        self.can_ip = IPv4Address
        self.can_port = 0
        self.last_transmission_time = None
        self.can_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)

        self.mac = "00:0C:29:DE:AD:BE"

    def __findpath(log_name):
        base_dir = path.abspath(getcwd())
        for root, dirs, files in walk(base_dir):
            for name in dirs:
                if name == "Logs":
                    log_path = path.join(root, name)
                    return path.join(log_path, log_name)
        log_path = path.join(base_dir, "Logs")
        return path.join(log_path, log_name)
    
    def __init_logging(self) -> None:
        filename = self.__findpath("sss3_log")
        logging.basicConfig(
            format='%(asctime)s - %(filename)s - %(levelname)s - %(message)s',
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
        # self.logger = logging.getLogger(__name__)
        # self.logger.setLevel(logging.DEBUG)
    
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

    def start_session(self, _ip: IPv4Address, _port: int) -> None:
        self.can_ip = _ip
        self.can_port = _port
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