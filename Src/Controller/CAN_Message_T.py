class CAN_Message_T:
    def __init__(
        self,
        can_id: int,
        timestamp: int,
        id_hit: int,
        extended: bool,
        remote: bool,
        overrun: bool,
        reserved: bool,
        data_length: int,
        data: bytes,
        mailbox: int,
        bus: int,
        sequential_frame: bool
        ) -> None:
        self.can_id = can_id
        self.timestamp = timestamp
        self.id_hit = id_hit
        self.extended = extended
        self.remote = remote
        self.overrun = overrun
        self.reserved = reserved
        self.data_length = data_length
        self.data = data
        self.mailbox = mailbox
        self.bus = bus
        self.sequential_frame = sequential_frame

    def __repr__(self) -> str:
        return (
            f'\tID: {self.can_id} Timestamp: {self.timestamp} IDHit: {self.id_hit}\n'
            f'\tExtended: {self.extended} Remote: {self.remote} Overrun: {self.overrun} Reserved: {self.reserved}\n'
            f'\tLength: {self.data_length} Data: {self.data}\n'
            f'\tMailbox: {self.mailbox} Bus: {self.bus} SeqFrame: {self.sequential_frame}\n'
            )