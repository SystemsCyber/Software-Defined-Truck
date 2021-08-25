import queue
import time
from typing import Tuple

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