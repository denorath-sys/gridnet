import unittest

from gridnet_sim.address import BROADCAST, Address
from gridnet_sim.packet import MAX_PAYLOAD, MessageType, Packet, PacketError


class TestAddress(unittest.TestCase):
    def test_parse_and_format_round_trip(self):
        addr = Address.parse("01.03.07.12")
        self.assertEqual(str(addr), "01.03.07.12")
        self.assertEqual(addr.to_bytes(), bytes([1, 3, 7, 12]))

    def test_from_bytes_round_trip(self):
        addr = Address.from_bytes(bytes([1, 3, 7, 12]))
        self.assertEqual(addr, Address.parse("01.03.07.12"))

    def test_broadcast_is_all_ff(self):
        self.assertEqual(BROADCAST.to_bytes(), b"\xff\xff\xff\xff")

    def test_ordering_matches_numeric_address(self):
        self.assertLess(Address.parse("01.03.07.11"), Address.parse("01.03.07.12"))
        self.assertLess(Address.parse("01.03.06.99"), Address.parse("01.03.07.01"))

    def test_out_of_range_component_rejected(self):
        with self.assertRaises(ValueError):
            Address(1, 3, 7, 256)


class TestPacket(unittest.TestCase):
    def setUp(self):
        self.src = Address.parse("01.03.07.11")
        self.dst = Address.parse("01.03.07.12")

    def test_encode_decode_round_trip(self):
        pkt = Packet(src=self.src, dst=self.dst, seq=42, type=MessageType.MSG, payload=b"hello")
        frame = pkt.encode()
        decoded = Packet.decode(frame)
        self.assertEqual(decoded.src, self.src)
        self.assertEqual(decoded.dst, self.dst)
        self.assertEqual(decoded.seq, 42)
        self.assertEqual(decoded.type, MessageType.MSG)
        self.assertEqual(decoded.payload, b"hello")

    def test_empty_payload_round_trips(self):
        pkt = Packet(src=self.src, dst=self.dst, seq=1, type=MessageType.ACK, payload=b"")
        decoded = Packet.decode(pkt.encode())
        self.assertEqual(decoded.payload, b"")

    def test_max_payload_round_trips(self):
        payload = bytes(range(256)) if MAX_PAYLOAD == 256 else b"x" * MAX_PAYLOAD
        pkt = Packet(src=self.src, dst=self.dst, seq=1, type=MessageType.APP_DATA, payload=payload)
        decoded = Packet.decode(pkt.encode())
        self.assertEqual(decoded.payload, payload)

    def test_payload_over_max_rejected(self):
        with self.assertRaises(ValueError):
            Packet(src=self.src, dst=self.dst, seq=1, type=MessageType.MSG, payload=b"x" * (MAX_PAYLOAD + 1))

    def test_corrupted_frame_fails_crc(self):
        pkt = Packet(src=self.src, dst=self.dst, seq=1, type=MessageType.MSG, payload=b"hello")
        frame = bytearray(pkt.encode())
        frame[-1] ^= 0xFF
        with self.assertRaises(PacketError):
            Packet.decode(bytes(frame))

    def test_bad_preamble_rejected(self):
        pkt = Packet(src=self.src, dst=self.dst, seq=1, type=MessageType.MSG, payload=b"hello")
        frame = bytearray(pkt.encode())
        frame[0] ^= 0xFF
        with self.assertRaises(PacketError):
            Packet.decode(bytes(frame))

    def test_seq_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            Packet(src=self.src, dst=self.dst, seq=70000, type=MessageType.MSG)

    def test_key_is_src_and_seq(self):
        pkt = Packet(src=self.src, dst=self.dst, seq=7, type=MessageType.MSG)
        self.assertEqual(pkt.key(), (self.src, 7))


if __name__ == "__main__":
    unittest.main()
