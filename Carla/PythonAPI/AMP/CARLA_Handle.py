import struct
import time
import queue
import socket
import json
from typing import Tuple, List


class CARLAHandle:
    def __init__(self, addr: Tuple[str, int], start: bytes, mac: str) -> None:
        self.addr = addr[0]
        self.port = addr[1]
        self.mac = mac
        self.start = struct.unpack("?", start)[0]
        self.type = "CARLA Client"
        self.heartbeat = time.time()
        self.out = queue.SimpleQueue()

    def send_setup(self, addr: str, carla: int, can: int) -> None:
        setup_message = json.dump({
            "mcast_ip":addr,
            "carla_port":carla,
            "can_port":can
        })
        content_length = struct.pack("!H", len(setup_message))
        self.out.put(content_length + setup_message)

    def send_device_list(self, SSS3s: List) -> None:
        device_list = json.dumps({
            "devices": [i.attached_device for i in SSS3s]
        })
        content_length = struct.pack("!H", len(device_list))
        self.out.put(content_length + device_list)
        self.start = False