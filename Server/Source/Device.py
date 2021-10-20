import queue
import time
import selectors
from typing import Tuple, Dict, List

SEL = selectors.SelectorKey

class Device:
    def __init__(self, read, write, addr: Tuple[str, int]) -> None:
        self.read = read
        self.write = write
        self.callback = read
        self.addr = addr
        self.accept_by = time.time() + 30
        self.logged_connection_close = False
        self.MAC = None
        self.type = "unknown"
        self.in_use = False
        self.outgoing_messages = queue.SimpleQueue()
        self.rate = 100.0 # 100 messages per second
        self.allowance = self.rate
        self.last_check = time.time()
        self.logged_rate_limit = False
        self.expecting_response = False
        self.response = None
    
    def rate_limit(self, log_error) -> bool:
        # Token Bucket algorithm
        now = time.time()
        self.allowance += (now - self.last_check) * self.rate
        self.last_check = now
        if (self.allowance > self.rate):
            self.allowance = self.rate
        if (self.allowance < 1.0):
            if not self.logged_rate_limit:
                log_error(f'Rate limiting {self.addr[0]}')
            return True
        else:
            self.logged_rate_limit = False
            self.allowance -= 1.0
            return False

    def is_loose(self, current_time: float, log_error) -> bool:
        if self.MAC:
            return False
        elif self.accept_by > current_time:
            return False
        elif not self.logged_connection_close:
            self.logged_connection_close = True
            msg = f'{self.addr[0]} has not registered within 30 '
            msg += f'seconds of first connecting. Closing connection.'
            log_error(msg)
            return True
        else:
            return True

    @staticmethod
    def is_registered(key: SEL) -> bool:
        if hasattr(key.data, "MAC") and key.data.MAC:
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
        if hasattr(key.data, "MAC") and key.data.MAC:
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