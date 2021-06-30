import socket
import numpy as np
import time

# sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
# sock.bind(("127.0.0.1", 8080))

#TCP Notes
# Carla Signal Address
# Carla Signal Port
# CAN Address
# CAN Port

while True:
    sock.sendto(b'Hello World!', ('224.1.1.1', 5007))
    time.sleep(1)
    # data, addr = sock.recvfrom(64)
    # in_np_array = np.frombuffer(data)
    #print(f'  Throttle: {in_np_array[0]}\tSteer: {in_np_array[1]}\tBrake: {in_np_array[2]}')
    #print(f'  Reverse:  {in_np_array[3]}\tHand Brake: {in_np_array[4]}\tManual: {in_np_array[5]}\tGear: {in_np_array[6]}')
    # as_byte_array = in_np_array.tobytes()
    # sock.sendto(as_byte_array, ("127.0.0.1", 8081))