"""CRC16 for packet integrity checking.

docs/protocol.md specifies a 2-byte "CRC16" trailer but does not name a
polynomial/init value. This implements CRC-16/CCITT-FALSE (poly 0x1021,
init 0xFFFF) since it's the common choice for low-bandwidth embedded links
(and matches what ST7580-adjacent stacks typically use). Swap this out if
the firmware team settles on a different variant — everything else in the
simulator is independent of the exact algorithm.
"""

_POLY = 0x1021
_INIT = 0xFFFF


def crc16_ccitt_false(data: bytes) -> int:
    crc = _INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
