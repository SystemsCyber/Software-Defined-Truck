import socket
import numpy as np
import struct

class ECMControl:

    def __init__(self, ip="127.0.0.1", port=8080) -> None:
        self.frame_num = np.uint32(0)
        self.last_frame = np.uint32(0)
        self.ip = ip
        self.port = port
        self.sock_tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # Socket for internet and UDP
        self.sock_tx.bind(('', self.port))
        self.sock_rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # Socket for internet and UDP
        self.sock_rx.bind(('', self.port + 1))
        self.sock_rx.settimeout(0.04)
        self.dropped_messages = 0
        self.timeouts = 0
        self.seq_miss_match = 0

    def increase_frame(self) -> None:
        self.frame_num += 1

    def send_frame_information(self, control):
        self.sock_tx.sendto(self.create_byte_array(control), (self.ip, self.port))
        self.last_frame = self.frame_num
        self.receive_ecm_information(control)

    def receive_ecm_information(self, control):
        try:
            data = self.sock_rx.recv(20)
            if len(data) == 20:  # 20 is size of carla struct in bytes
                ecm_data = struct.unpack("Ifff???B", data)
                if ecm_data[0] >= self.last_frame:
                    self.print_frame(ecm_data)
                    control.throttle = ecm_data[1]
                    control.steer = ecm_data[2]
                    control.brake = ecm_data[3]
                    control.hand_brake = ecm_data[4]
                    control.reverse = ecm_data[5]
                    control.manual_gear_shift = ecm_data[6]
                    control.gear = ecm_data[7]
                else:
                    self.dropped_messages += 1
                    self.seq_miss_match += 1
                    self.sock_rx.settimeout(0.01)
                    for i in range(self.last_frame - ecm_data[0]):
                        self.sock_rx.recv(20)
                        self.dropped_messages += 1
                        self.seq_miss_match += 1
                    self.sock_rx.settimeout(0.04)
                    print(ecm_data[0])
                    print(self.last_frame)
                    print(f'Sequence number miss match. Total: {self.seq_miss_match}')
        except socket.timeout:
            self.sock_rx.settimeout(0.04)
            self.dropped_messages += 1
            self.timeouts += 1
            print(f'Socket Timeout. Total: {self.timeouts}')
        except socket.error:
            self.sock_rx.settimeout(0.04)
            self.dropped_messages += 1
            print(f'Socket Error.')

    def create_byte_array(self, control):
        return struct.pack("Ifff???B",
                    np.uint32(self.frame_num),     # Frame number
                    np.float32(control.throttle),  # Throttle
                    np.float32(control.steer),     # Steering
                    np.float32(control.brake),     # Braking
                    control.hand_brake,            # Hand Brake
                    control.reverse,               # Reverse
                    control.manual_gear_shift,     # Manual
                    np.uint8(control.gear))        # Gear

    def print_frame(self, frame) -> None:
        print(f'Frame: {frame[0]:<8,}')
        print(f'Throttle: {frame[1]:0<.4f}  Steer:   {frame[2]:0<.4f}  Brake:  {frame[3]:0<.4f}')
        print(f'Reverse:  {frame[4]:<5}  E-Brake: {frame[5]:<5}  ' \
                f'Manual: {frame[6]:<5}  Gear: {frame[7]}\n')

        #Frame: 12345678
        #Throttle: 1.1234  Steer:   1.1234  Brake:  1.1234
        #Reverse:  Falsee  E-Brake: Falsee  Manual: Falsee  Gear: 1