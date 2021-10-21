from ctypes import *

class FLAGS_FD(Structure):
    _fields_ = [
        ("extended", c_bool),
        ("overrun", c_bool),
        ("reserved", c_bool)
        ]

    def __repr__(self) -> str:
        return (
            f'\textended: {self.extended} overrun: {self.overrun} reserved: {self.reserved}\n'
        )

class CANFD_message_t(Structure):
    _fields_ = [
        ("can_id", c_uint32),
        ("can_timestamp", c_uint16),
        ("idhit", c_uint8),
        ("brs", c_bool),
        ("esi", c_bool),
        ("edl", c_bool),
        ("flags", FLAGS_FD),
        ("len", c_uint8),
        ("buf", c_uint8 * 64),
        ("mb", c_int8),
        ("bus", c_uint8),
        ("seq", c_bool)
        ]

    def __repr__(self) -> str:
        return (
            f'\tcan_id: {self.can_id} can_timestamp: {self.can_timestamp} idhit: {self.id_hit}\n'
            f'\tbrs: {self.brs} esi: {self.esi} edl: {self.edl}\n'
            f'{self.flags}'
            f'\tlen: {self.len} buf: {self.buf}\n'
            f'\tmb: {self.mb} bus: {self.bus} seq: {self.seq}\n'
            )


class FLAGS(Structure):
    _fields_ = [
        ("extended", c_bool),
        ("remote", c_bool),
        ("overrun", c_bool),
        ("reserved", c_bool)
        ]

    def __repr__(self) -> str:
        return (
            f'\textended: {self.extended} remote: {self.remote} overrun: {self.overrun} reserved: {self.reserved}\n'
        )

class CAN_message_t(Structure):
    _fields_ = [
        ("can_id", c_uint32),
        ("can_timestamp", c_uint16),
        ("idhit", c_uint8),
        ("flags", FLAGS),
        ("len", c_uint8),
        ("buf", c_uint8 * 8),
        ("mb", c_int8),
        ("bus", c_uint8),
        ("seq", c_bool)
        ]

    def __repr__(self) -> str:
        return (
            f'\tcan_id: {self.can_id} can_timestamp: {self.can_timestamp} idhit: {self.id_hit}\n'
            f'{self.flags}'
            f'\tlen: {self.len} buf: {self.buf}\n'
            f'\tmb: {self.mb} bus: {self.bus} seq: {self.seq}\n'
            )


class WCANFrame(Union):
    _fields_ = [
        ("can_frame", CAN_message_t),
        ("can_frame", CANFD_message_t)
    ]


class COMMBLOCK(Structure):
    _fields_ = [
        ("id", c_uint32),
        ("frame_number", c_uint32)
    ]

    def __repr__(self) -> str:
        return (
            f'Device: {self.id} Frame Number: {self.frame_number}\n'
        )

class WCANBlock(COMMBLOCK):
    _anonymous_ = ("can_frame",)
    _fields_ = [
        ("type", c_uint8),
        ("sequence_number", c_uint32),
        ("timestamp", c_uint32),
        ("need_response", c_bool),
        ("can_frame", WCANFrame)
        ("can_frame", CAN_message_t)
    ]

    def __repr__(self) -> str:
        return (
            f'Type: {self.type} Sequence Number: {self.sequence_number}\n'
            f'Timestamp: {self.timestamp} Need Response: {self.need_response}\n'
            f'Can Frame: \n{self.can_frame}'
        ) + super().__repr__()

class WSenseBlock(COMMBLOCK):
    _fields_ = [
        ("type", c_uint8),
        ("num_signals", c_uint8),
        ("signals", POINTER(c_float))
    ]

    def __repr__(self) -> str:
        return (
            f'type: {self.type} num_signals: {self.num_signals}\n'
        ) + super().__repr__()
