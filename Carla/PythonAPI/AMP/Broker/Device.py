import queue
import time
import selectors
from typing import Tuple, Dict, List

SEL = selectors.SelectorKey

class Device:
    def __init__(self, callback, addr: Tuple[str, int]) -> None:
        self.callback = callback
        self.addr = addr
        self.accept_by = time.time() + 5
        self.MAC = "unknown"
        self.type = "unknown"
        self.in_use = False
        self.outgoing_messages = queue.SimpleQueue()
        self.rate = 10.0 # 10 messages per second
        self.allowance = self.rate
        self.last_check = time.time()

    @staticmethod
    def is_registered(key: SEL) -> bool:
        if hasattr(key.data, "MAC") and key.data.MAC != "unknown":
            return True
        return False

    @staticmethod
    def is_not_listening_socket(key: SEL) -> bool:
        return hasattr(key.data, "MAC")

    @staticmethod
    def is_client(key: SEL) -> bool:
        if Device.is_registered(key):
            return hasattr(key.data, "type") and key.data.type == "CLIENT"
        else:
            return False
    
    @staticmethod
    def is_SSS3(key: SEL) -> bool:
        if hasattr(key.data, "MAC") and key.data.MAC != "unknown":
            return hasattr(key.data, "type") and key.data.type == "SSS3"
        else:
            return False

    @staticmethod
    def is_available(key: SEL) -> bool:
        if Device.is_not_listening_socket(key):
            return Device.is_SSS3(key) and not key.data.in_use

    @staticmethod
    def get_available_ECUs(sel: selectors.DefaultSelector) -> List:
        available = []
        sel_map = sel.get_map()
        for fd in sel_map:
            key = sel_map[fd]
            if Device.is_available(key):
                available.append({
                    "ID": fd, 
                    "ECUs": key.data.ECUs
                })
        return available