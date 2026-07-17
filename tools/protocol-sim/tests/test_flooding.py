import random
import unittest

from gridnet_sim.address import Address
from gridnet_sim.medium import Medium
from gridnet_sim.node import Node
from gridnet_sim.packet import MessageType, Packet
from gridnet_sim.simulator import Simulator


def _count_transmissions(medium: Medium):
    """Wrap medium.transmit to count how many times each node_id transmits a
    given (src, seq) packet — used to assert 'each device repeats once'."""
    counts = {}
    original = medium.transmit

    def wrapped(sim, node_id, frame):
        pkt = Packet.decode(frame)
        counts[(node_id, pkt.key())] = counts.get((node_id, pkt.key()), 0) + 1
        original(sim, node_id, frame)

    medium.transmit = wrapped
    return counts


class TestMultihopFlood(unittest.TestCase):
    def test_message_reaches_destination_via_relay(self):
        sim = Simulator()
        sim.log_events = False
        seg_a = Medium("seg-a", bitrate_bps=4800, rng=random.Random(42))
        seg_c = Medium("seg-c", bitrate_bps=4800, rng=random.Random(43))

        a = Node(sim, Address.parse("01.01.01.01"), plc_medium=seg_a)
        relay = Node(sim, Address.parse("01.01.01.02"), plc_medium=seg_a)
        relay.attach_wifi(seg_c)
        c = Node(sim, Address.parse("01.01.02.01"), plc_medium=seg_c)

        a.send_message(c.address, b"ping")
        sim.run(10)

        self.assertEqual(len(c.inbox), 1)
        self.assertEqual(c.inbox[0].payload, b"ping")
        self.assertEqual(a.outbox, [])  # ACK came back and cleared it

    def test_relay_does_not_echo_back_to_arrival_medium(self):
        sim = Simulator()
        sim.log_events = False
        seg_a = Medium("seg-a", bitrate_bps=4800, rng=random.Random(42))
        seg_c = Medium("seg-c", bitrate_bps=4800, rng=random.Random(43))
        counts_a = _count_transmissions(seg_a)

        a = Node(sim, Address.parse("01.01.01.01"), plc_medium=seg_a)
        relay = Node(sim, Address.parse("01.01.01.02"), plc_medium=seg_a)
        relay.attach_wifi(seg_c)
        c = Node(sim, Address.parse("01.01.02.01"), plc_medium=seg_c)

        pkt = a.send_message(c.address, b"ping")
        sim.run(10)

        # the relay must never have retransmitted onto the segment it heard the packet on
        self.assertNotIn((relay.id, pkt.key()), counts_a)

    def test_diamond_topology_delivers_exactly_once(self):
        """Two independent relays (B and D) both bridge seg1<->seg2 — C has two
        paths to A. Loop/duplicate prevention must still deliver exactly once."""
        sim = Simulator()
        sim.log_events = False
        rng = random.Random(1234)
        seg1 = Medium("seg1", bitrate_bps=4800, rng=rng)
        seg2 = Medium("seg2", bitrate_bps=4800, rng=rng)

        a = Node(sim, Address.parse("01.01.01.01"), plc_medium=seg1)
        b = Node(sim, Address.parse("01.01.01.02"), plc_medium=seg1)
        b.attach_wifi(seg2)
        d = Node(sim, Address.parse("01.01.01.03"), plc_medium=seg1)
        d.attach_wifi(seg2)
        c = Node(sim, Address.parse("01.01.02.01"), plc_medium=seg2)

        a.send_message(c.address, b"ping")
        sim.run(10)

        self.assertEqual(len(c.inbox), 1)

    def test_duplicate_frames_are_not_reprocessed(self):
        sim = Simulator()
        sim.log_events = False
        seg = Medium("seg", bitrate_bps=4800, rng=random.Random(42))
        a = Node(sim, Address.parse("01.01.01.01"), plc_medium=seg)
        b = Node(sim, Address.parse("01.01.01.02"), plc_medium=seg)

        pkt = Packet(src=a.address, dst=b.address, seq=1, type=MessageType.MSG, payload=b"x")
        frame = pkt.encode()
        # inject the same frame twice, simulating a collision-domain echo/retransmit
        b._on_receive_raw(frame, seg)
        b._on_receive_raw(frame, seg)

        self.assertEqual(len(b.inbox), 1)


if __name__ == "__main__":
    unittest.main()
