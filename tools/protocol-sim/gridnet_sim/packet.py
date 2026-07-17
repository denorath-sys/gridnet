"""GRIDNET packet framing (docs/protocol.md).

Wire format:

    [AA AA AA] [55] [LEN 2B] [SRC 4B] [DST 4B] [SEQ 2B] [TYPE 1B] [PAYLOAD] [CRC16 2B]
     preamble    sync   len     source    dest     seq      type      data      checksum

LEN is the payload length. CRC16 is computed over everything from LEN through
PAYLOAD inclusive (preamble/sync are link-framing, not covered by the check —
this is an assumption, see gridnet_sim/crc16.py).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum

from .address import Address
from .crc16 import crc16_ccitt_false

PREAMBLE = b"\xaa\xaa\xaa"
SYNC = b"\x55"
MAX_PAYLOAD = 256


class MessageType(IntEnum):
    MSG = 0x01
    ACK = 0x02
    BROADCAST = 0x03
    ROUTE = 0x04
    MASTER_ALIVE = 0x05
    MASTER_RESIGN = 0x06
    APP_DATA = 0x10
    GAME_STATE = 0x11
    GAME_ACTION = 0x12


class PacketError(ValueError):
    """Raised on malformed framing or a CRC mismatch."""


@dataclass
class Packet:
    src: Address
    dst: Address
    seq: int
    type: MessageType
    payload: bytes = field(default=b"")

    def __post_init__(self) -> None:
        if not 0 <= self.seq <= 0xFFFF:
            raise ValueError(f"seq={self.seq} out of range 0..65535")
        if len(self.payload) > MAX_PAYLOAD:
            raise ValueError(
                f"payload is {len(self.payload)} bytes, max is {MAX_PAYLOAD}"
            )

    def encode(self) -> bytes:
        body = (
            struct.pack(">H", len(self.payload))
            + self.src.to_bytes()
            + self.dst.to_bytes()
            + struct.pack(">H", self.seq)
            + struct.pack("B", int(self.type))
            + self.payload
        )
        crc = crc16_ccitt_false(body)
        return PREAMBLE + SYNC + body + struct.pack(">H", crc)

    @classmethod
    def decode(cls, data: bytes) -> "Packet":
        if len(data) < len(PREAMBLE) + len(SYNC) + 13 + 2:
            raise PacketError(f"frame too short: {len(data)} bytes")
        if data[: len(PREAMBLE)] != PREAMBLE:
            raise PacketError("bad preamble")
        offset = len(PREAMBLE)
        if data[offset : offset + 1] != SYNC:
            raise PacketError("bad sync byte")
        offset += 1

        (payload_len,) = struct.unpack_from(">H", data, offset)
        offset += 2
        src = Address.from_bytes(data[offset : offset + 4])
        offset += 4
        dst = Address.from_bytes(data[offset : offset + 4])
        offset += 4
        (seq,) = struct.unpack_from(">H", data, offset)
        offset += 2
        (type_byte,) = struct.unpack_from("B", data, offset)
        offset += 1

        body_start = len(PREAMBLE) + len(SYNC)
        payload_end = offset + payload_len
        if payload_end + 2 > len(data):
            raise PacketError("payload length exceeds frame size")
        payload = data[offset:payload_end]

        body = data[body_start:payload_end]
        (crc_received,) = struct.unpack_from(">H", data, payload_end)
        crc_computed = crc16_ccitt_false(body)
        if crc_received != crc_computed:
            raise PacketError(
                f"CRC mismatch: got {crc_received:#06x}, expected {crc_computed:#06x}"
            )

        try:
            msg_type = MessageType(type_byte)
        except ValueError:
            raise PacketError(f"unknown message type {type_byte:#04x}") from None

        return cls(src=src, dst=dst, seq=seq, type=msg_type, payload=payload)

    def key(self) -> tuple:
        """Identity used for flood dedup — a given (src, seq) is only ever repeated once."""
        return (self.src, self.seq)

    def __str__(self) -> str:
        return (
            f"{self.type.name} {self.src}->{self.dst} seq={self.seq} "
            f"({len(self.payload)}B)"
        )
