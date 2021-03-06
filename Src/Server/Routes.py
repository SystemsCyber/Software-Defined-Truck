from types import FunctionType
from typing import Dict

routes: Dict[str, FunctionType] = {}


def add(path: str, method: str) -> FunctionType:
    def update(func: FunctionType) -> FunctionType:
        global routes
        routes[path.upper()+method.upper()] = func
        return func
    return update
