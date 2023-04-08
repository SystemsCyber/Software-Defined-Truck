from __future__ import annotations

import logging
import platform
import re
import subprocess
import selectors as sel
import socket as soc
from ctypes import (Structure, Union, c_bool, c_int8, c_uint8, c_uint16,
                    c_uint32, sizeof, memmove, addressof, byref, Array, c_byte)
from enum import Enum, auto
from ipaddress import IPv4Address
from types import SimpleNamespace
from typing import List, Tuple, Type

from getmac import get_mac_address as gma

from multiprocessing import Lock, Event, RLock
from time import time_ns, perf_counter_ns


class CANFD_message(Structure):
    _pack_ = 4
    _fields_ = [
        ("can_id", c_uint32),
        ("len", c_uint8),
        ("flags", c_uint8),
        ("buf", c_uint8 * 64),
    ]

    def __repr__(self) -> str:
        return (
            f'\tcan_id: {self.can_id} len: {self.len} flags: {self.flags}\n'
            f'\tbuf: {self.buf}\n'
        )


class CAN_message(Structure):
    _pack_ = 4
    _fields_ = [
        ("can_id", c_uint32),
        ("len", c_uint8),
        ("buf", c_uint8 * 8)
    ]

    def __repr__(self) -> str:
        return f'\tcan_id: {self.can_id} len: {self.len} buf: {self.buf}\n'


class WCANFrame(Union):
    _pack_ = 4
    _fields_ = [
        ("can", CAN_message),
        ("can_fd", CANFD_message)
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


class Member_Node():
    def __init__(self, _id=-1, _devices=[]) -> None:
        self.id = _id
        self.devices = _devices
        self.last_received_frame = 1
        self.last_seq_num = 1
        self.health_report = None


class CANNode(object):
    class SessionStatus(Enum):
        Inactive = auto()
        Active = auto()

    def __init__(self, *args, **kwargs) -> None:
        self.__can_ip = IPv4Address
        self.__can_port = 0
        self.sel = sel.DefaultSelector()
        self.sel_lock = RLock()
        self._recv_size = 0
        self._recv_addr = None
        self.__inital_time = time_ns()

        self.mac = gma()
        self._sequence_number = 1
        self.session_status = self.SessionStatus.Inactive
        self._can_block_packed_size = 76
        self.mac = "00:0C:29:DE:AD:BE"  # For testing purposes
        logging.debug(f"The testing MAC address is: {self.mac}")
        self.sending_sync = False
        self.sync_timestamp = 0
        self.sync_sent_timestamp = 0

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

    def __get_ip_addresses_and_gateway(self) -> Tuple[list[str], str]:
        system = platform.system()
        if system == "Linux":
            command = "ip addr show"
        elif system == "Windows":
            command = "ipconfig /all"
        else:
            raise Exception("Unsupported operating system")
        output = subprocess.run(
            command.split(), capture_output=True, text=True).stdout
        ipv4_pattern = r"(?P<ip>(?:[0-9]{1,3}\.){3}[0-9]{1,3})"
        ipv4_addresses = []
        gateway = None
        for line in output.split("\n"):
            match = re.search(ipv4_pattern, line)
            if match:
                print(line)
                ipv4_address = match.group("ip")
                if system == "Linux" and "scope global" in line:
                    ipv4_addresses.append(ipv4_address)
                elif system == "Windows" and "IPv4 Address" in line:
                    ipv4_addresses.append(ipv4_address)
                elif system == "Windows" and "Default Gateway" in line:
                    gateway = ipv4_address
                elif system == "Linux" and "default via" in line:
                    gateway = ipv4_address
        if gateway is None:
            raise Exception("Could not find gateway")
        logging.info(f"Device gateway: {gateway}")
        logging.info(f"Device interface IP addresses: {ipv4_addresses}")
        return ipv4_addresses, gateway

    def __get_closest_ip_address(self, ipv4_addresses: list[str], gateway: str) -> str:
        closest_ip_address = None
        closest_distance = None
        gw = IPv4Address(gateway)
        for ipv4_address in ipv4_addresses:
            ip = IPv4Address(ipv4_address)
            distance = abs(int(gw) - int(ip))
            if closest_distance is None or distance < closest_distance:
                closest_distance = distance
                closest_ip_address = ipv4_address
        logging.debug(
            f"Distance between {closest_ip_address} and {gateway} is {closest_distance}")
        if closest_ip_address is None:
            raise Exception("Could not find closest IP address")
        return closest_ip_address

    def __create_group_info(self, can_ip: IPv4Address) -> Tuple[bytes, bytes]:
        ipv4_addresses, gateway = self.__get_ip_addresses_and_gateway()
        closest_ip_address = self.__get_closest_ip_address(
            ipv4_addresses, gateway)
        logging.info(f"Multicast interface chosen: {closest_ip_address}")
        iface = soc.inet_aton(closest_ip_address)
        group = soc.inet_aton(str(can_ip))
        mreq = group + iface
        return iface, mreq

    def start_session(self, _ip: IPv4Address, _port: int) -> None:
        self.__can_ip = _ip
        self.__str_can_ip = str(self.__can_ip)
        self.__can_port = _port
        self.__iface, self.__mreq = self.__create_group_info(self.__can_ip)
        self.__init_socket(self.__can_port, self.__mreq,
                           self.__iface)  # type: ignore
        can_data = SimpleNamespace(callback=self.read, message=None)
        with self.sel_lock:
            self.can_key = self.sel.register(
                self.__can_sock, sel.EVENT_READ, can_data)
        self.session_status = self.SessionStatus.Active

    def read(self) -> bytes:
        try:
            return self.__can_sock.recv(1024)
        except OSError as oe:
            logging.debug("Occured in read")
            logging.error(oe)
            return bytes()

    def unpack_canblock(self, frame: WCANBlock, buffer: bytes, offset: int) -> None:
        frame.sequence_number = int.from_bytes(
            buffer[offset:offset + 4], "little")
        offset += 4
        frame.need_response = bool.from_bytes(
            buffer[offset:offset + 1], "little")
        offset += 1
        frame.fd = bool.from_bytes(buffer[offset:offset + 1], "little")
        offset += 1
        if frame.fd == True:
            frame.can_fd.can_id = int.from_bytes(
                buffer[offset:offset + 4], "little")
            offset += 4
            frame.can_fd.len = int.from_bytes(
                buffer[offset:offset + 1], "little")
            offset += 1
            frame.can_fd.flags = int.from_bytes(
                buffer[offset:offset + 1], "little")
            offset += 1
            memmove(frame.can_fd.buf, buffer[offset:offset + frame.can_fd.len], frame.can_fd.len)
        else:
            frame.can.can_id = int.from_bytes(buffer[offset:offset + 4], "little")
            offset += 4
            frame.can.len = int.from_bytes(buffer[offset:offset + 1], "little")
            offset += 1
            memmove(frame.can.buf, buffer[offset:offset + frame.can.len], frame.can.len)

    def pack_canblock(self, frame: WCANBlock, buffer: bytearray) -> None:
        buffer.extend(frame.sequence_number.to_bytes(4, "little"))
        buffer.extend(frame.need_response.to_bytes(1, "little"))
        buffer.extend(frame.fd.to_bytes(1, "little"))
        if frame.fd:
            buffer.extend(frame.can_fd.can_id.to_bytes(4, "little"))
            buffer.extend(frame.can_fd.len.to_bytes(1, "little"))
            buffer.extend(frame.can_fd.flags.to_bytes(1, "little"))
            for i in range(frame.can_fd.len):
                buffer.extend(frame.can_fd.buf[i].to_bytes(1, "little"))
        else:
            buffer.extend(frame.can.can_id.to_bytes(4, "little"))
            buffer.extend(frame.can.len.to_bytes(1, "little"))
            for i in range(frame.can.len):
                buffer.extend(frame.can.buf[i].to_bytes(1, "little"))

    def write(self, message: bytes) -> int:
        try:
            temp = self.__can_sock.sendto(
                message,
                (self.__str_can_ip, self.__can_port)
            )
            if self.sending_sync:
                self.sync_sent_timestamp = self.time_us()
                self.sending_sync = False
            return temp
        except OSError as oe:
            logging.error(oe)
            return 0

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

    def time_us(self) -> int:
        return (self.__inital_time + perf_counter_ns()) // 1000
