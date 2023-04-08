import socket
import ctypes
from ctypes import c_uint32, c_uint8, c_uint64, c_float
from bytearrayClient import Type1, Type2, MessageData, Message

def unpack_message(data):
    message = Message()
    offset = 0

    message.counter = int.from_bytes(data[offset:offset+4], 'little')
    offset += 4

    message.message_type = int.from_bytes(data[offset:offset+1], 'little')
    offset += 1

    if message.message_type == 1:
        message.data.type1_data.current_time_ms = int.from_bytes(data[offset:offset+8], 'little')
        offset += 8
        message.data.type1_data.random_number = int.from_bytes(data[offset:offset+1], 'little')
    else:
        for i in range(10):
            message.data.type2_data.random_numbers[i] = ctypes.c_float.from_buffer_copy(data[offset:offset+4])
            offset += 4

    return message

def main():
    server_address = ("", 12346)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(server_address)

    while True:
        data, addr = sock.recvfrom(1024)
        message = unpack_message(data)

        if message.counter % 100 == 0:
            print(f"Counter: {message.counter}, Message Type: {message.message_type}")

            if message.message_type == 1:
                print(f"Time (ms): {message.data.type1_data.current_time_ms}, Random Number: {message.data.type1_data.random_number}")
            else:
                print(f"Random Floats: {[num for num in message.data.type2_data.random_numbers]}")

            print("")

if __name__ == "__main__":
    main()

