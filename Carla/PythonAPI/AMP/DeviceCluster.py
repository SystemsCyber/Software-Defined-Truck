import threading
import selectors
from collections.abc import MutableSequence


class DeviceCluster(MutableSequence):
    def __init__(self, init=None) -> None:
        self._cluster = []
        self._cluster_lock = threading.Lock()
        self.sel = selectors.DefaultSelector()

    def __len__(self) -> int:
        with self._cluster_lock:
            return len(self._cluster)

    def __getitem__(self, index):
        with self._cluster_lock:
            return self._cluster[index]

    def __setitem__(self, index, value) -> None:
        with self._cluster_lock:
            self._cluster[index] = value

    def __delitem__(self, index):
        with self._cluster_lock:
            del self._cluster[index]

    def insert(self, index, value):
        with self._cluster_lock:
            self._cluster.insert(index, value)