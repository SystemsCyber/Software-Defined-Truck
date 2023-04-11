import socket
import ctypes
from ctypes import c_uint32, c_uint8, c_uint64, c_float, byref, memset
from ctypeClient import Type1, Type2, MessageData, Message
import time

def unpack_message(data, message):
    offset = 0

    ctypes.memmove(byref(message), byref(data, offset), 4)
    offset += 4

    ctypes.memmove(byref(message, 4), byref(data, offset), 1)
    offset += 1

    if message.message_type == 1:
        ctypes.memmove(byref(message, 8), byref(data, offset), 8)
        offset += 8
        ctypes.memmove(byref(message, 16), byref(data, offset), 1)
        offset += 1
    else:
        floatOffset = 8
        for i in range(10):
            ctypes.memmove(byref(message, floatOffset), byref(data, offset), 4)
            offset += 4
            floatOffset += 4
    return offset

def main():
    server_address = ("", 12345)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(server_address)

    buffer = (ctypes.c_char * 1024)()
    message = Message()

    while True:
        data_len, addr = sock.recvfrom_into(buffer)
        memset(byref(message), 0, ctypes.sizeof(message))
        # start = time.perf_counter_ns()
        size = unpack_message(buffer, message)
        # print(f"Time to unpack (us): {(time.perf_counter_ns() - start)//1000}")
        # print(f"Size of message: {size} bytes")

        if message.counter % 100 == 0:
            print(f"Counter: {message.counter}, Message Type: {message.message_type}")

            if message.message_type == 1:
                print(f"Time (ms): {message.data.type1_data.current_time_ms}, Random Number: {message.data.type1_data.random_number}")
            else:
                print(f"Random Floats: {[num for num in message.data.type2_data.random_numbers]}")

            print("")

if __name__ == "__main__":
    main()
