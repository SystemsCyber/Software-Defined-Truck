import socket
import random
import time
import ctypes
from ctypes import Union, Structure, c_uint32, c_uint8, c_uint64, c_float, cdll, memset, byref

class Type1(Structure):
    _pack_ = 4
    _fields_ = [("current_time_ms", c_uint64),
                ("random_number", c_uint8)]

class Type2(Structure):
    _pack_ = 4
    _fields_ = [("random_numbers", c_float * 10)]

class MessageData(Union):
    _pack_ = 4
    _fields_ = [("type1_data", Type1),
                ("type2_data", Type2)]

class Message(Structure):
    _pack_ = 4
    _fields_ = [("counter", c_uint32),
                ("message_type", c_uint8),
                ("data", MessageData)]

def random_floats():
    return [random.uniform(-1, 1) for _ in range(10)]

def pack_message(message, buffer):
    offset = 0

    ctypes.memmove(byref(buffer, offset), byref(message), 4)
    offset += 4

    ctypes.memmove(byref(buffer, offset), byref(message, 4), 1)
    offset += 1

    if message.message_type == 1:
        ctypes.memmove(byref(buffer, offset), byref(message, 8), 8)
        offset += 8
        ctypes.memmove(byref(buffer, offset), byref(message, 16), 1)
        offset += 1
    else:
        floatOffset = 8
        for i in range(10):
            ctypes.memmove(byref(buffer, offset), byref(message, floatOffset), 4)
            offset += 4
            floatOffset += 4
    return offset

def main():
    server_address = ("localhost", 12345)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    counter = 0
    buffer = (ctypes.c_char * 100)()
    msg_per_sec = 0
    num_msgs = 0
    avg_times = []
    message = Message()
    true_start = time.perf_counter_ns()
    while True:
        message.counter = counter
        # message.message_type = random.randint(1, 2)
        message.message_type = 1

        if message.message_type == 1:
            message.data.type1_data.current_time_ms = int(time.time() * 1000)
            message.data.type1_data.random_number = random.randint(0, 255)
        else:
            message.data.type2_data.random_numbers = (c_float * 10)(*random_floats())

        memset(buffer, 0, ctypes.sizeof(buffer))
        start = time.perf_counter_ns()
        msg_size = pack_message(message, buffer)
        avg_times.append((time.perf_counter_ns() - start)//1000)
        if len(avg_times) % 100 == 0:
            num_msgs += 100
            msg_per_sec = num_msgs / ((time.perf_counter_ns() - true_start) / 1000000000)
            print("Avg packing time (us): ", sum(avg_times)/len(avg_times))
            print("Msgs per second: ", msg_per_sec)
            avg_times = []
        # print("Message size: ", msg_size)
        sock.sendto(buffer[:msg_size], server_address)
        # time.sleep(0.0001)
        counter += 1

if __name__ == "__main__":
    main()
