import socket
import random
import time
import ctypes
from ctypes import Union, Structure, c_uint32, c_uint8, c_uint64, c_float, c_char

class Type1(Structure):
    _fields_ = [("current_time_ms", c_uint64),
                ("random_number", c_uint8)]

class Type2(Structure):
    _fields_ = [("random_numbers", c_float * 10)]

class MessageData(Union):
    _fields_ = [("type1_data", Type1),
                ("type2_data", Type2)]

class Message(Structure):
    _fields_ = [("counter", c_uint32),
                ("message_type", c_uint8),
                ("data", MessageData)]

def random_floats():
    return [random.uniform(-1, 1) for _ in range(10)]

def pack_message(message):
    buffer = bytearray()
    buffer.extend(message.counter.to_bytes(4, 'little'))
    buffer.extend(message.message_type.to_bytes(1, 'little'))

    if message.message_type == 1:
        buffer.extend(message.data.type1_data.current_time_ms.to_bytes(8, 'little'))
        buffer.extend(message.data.type1_data.random_number.to_bytes(1, 'little'))
    else:
        temp_buffer = (c_char * 4)()
        for num in message.data.type2_data.random_numbers:
            ctypes.memmove(temp_buffer, ctypes.byref(ctypes.c_float(num)), 4)
            buffer.extend(temp_buffer)

    return buffer

def main():
    server_address = ("localhost", 12346)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    counter = 0
    avg_times = []
    message = Message()
    num_msgs = 0
    msg_per_sec = 0
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

        start = time.perf_counter_ns()
        packed_message = pack_message(message)
        avg_times.append((time.perf_counter_ns() - start) // 1000)
        if len(avg_times) % 100 == 0:
            num_msgs += 100
            msg_per_sec = num_msgs / ((time.perf_counter_ns() - true_start) / 1000000000)
            print(f"Average time to pack message (us): {sum(avg_times) // len(avg_times)}")
            print(f"Messages per second: {msg_per_sec}")
            avg_times = []
        sock.sendto(packed_message, server_address)
        # time.sleep(0.001)
        counter += 1

if __name__ == "__main__":
    main()
