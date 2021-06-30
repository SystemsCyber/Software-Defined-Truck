import struct
import time
import queue
import socket
from typing import Tuple


class SSS3Handle:
    def __init__(self, addr: Tuple[str, int], device: bytes, mac: str) -> None:
        self.addr = addr[0]
        self.port = addr[1]
        self.mac = mac
        device = struct.unpack("8cH11c11c", device)
        self.attached_device = {
            "type": ''.join([device[i].strip(b"\x00").decode() for i in range(0, 8)]),
            "year": device[8],
            "make": ''.join([device[i].strip(b"\x00").decode() for i in range(9, 20)]),
            "model": ''.join([device[i].strip(b"\x00").decode() for i in range(20, 31)]),
        }
        self.type = "SSS3"
        self.heartbeat = time.time()
        self.out = queue.SimpleQueue()

    def send_setup(self, addr: str, carla: int, can: int) -> None:
        mcast_ip = socket.inet_aton(addr)
        self.out.put(struct.pack("4sii", mcast_ip, carla, can))
