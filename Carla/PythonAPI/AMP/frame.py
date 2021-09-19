import struct


class Frame:
    def __init__(self) -> None:
        self.frame_num = 0
        self.last_frame = 0

    def pack(self, control) -> bytes:
        self.last_frame = self.frame_num
        return struct.pack("Ifff???B",
                           self.frame_num,              # Frame number
                           control.throttle,            # Throttle
                           control.steer,               # Steering
                           control.brake,               # Braking
                           control.hand_brake,          # Hand Brake
                           control.reverse,             # Reverse
                           control.manual_gear_shift,   # Manual
                           control.gear)                # Gear

    def unpack(self, ecm_data, control, verbose=False) -> bool:
        if ecm_data[0] >= self.last_frame:
            control.throttle = ecm_data[1]
            control.steer = ecm_data[2]
            control.brake = ecm_data[3]
            control.hand_brake = ecm_data[4]
            control.reverse = ecm_data[5]
            control.manual_gear_shift = ecm_data[6]
            control.gear = ecm_data[7]
            if verbose:
                self.print_frame(ecm_data)
            return True
        else:
            return False

    def print_frame(self, frame) -> None:
        print(f'Frame: {frame[0]:<8,}')
        print(
            f'Throttle: {frame[1]:0<.4f}  Steer:   {frame[2]:0<.4f}  Brake:  {frame[3]:0<.4f}')
        print(f'Reverse:  {frame[4]:<5}  E-Brake: {frame[5]:<5}  '
              f'Manual: {frame[6]:<5}  Gear: {frame[7]}\n')

        #Frame: 12345678
        # Throttle: 1.1234  Steer:   1.1234  Brake:  1.1234
        # Reverse:  Falsee  E-Brake: Falsee  Manual: Falsee  Gear: 1
