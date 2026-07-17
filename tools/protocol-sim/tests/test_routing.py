import random
import unittest

from gridnet_sim.address import Address
from gridnet_sim.medium import Medium
from gridnet_sim.node import (
    MAX_ROUTE_ENTRIES,
    MAX_ROUTE_HOPS,
    ROUTE_ADVERTISE_INTERVAL,
    ROUTE_STALE,
    Node,
    _pack_route_entries,
    _unpack_route_entries,
)
from gridnet_sim.packet import MessageType, Packet
from gridnet_sim.simulator import Simulator


def _node(sim, addr, medium, seed):
    return Node(sim, Address.parse(addr), plc_medium=medium, rng=random.Random(seed))


class TestRouteEntryCodec(unittest.TestCase):
    def test_pack_unpack_round_trip(self):
        entries = [(Address.parse("01.01.01.01"), 0), (Address.parse("01.01.01.02"), 3)]
        payload = _pack_route_entries(entries)
        self.assertEqual(list(_unpack_route_entries(payload)), entries)

    def test_max_entries_fit_in_one_payload(self):
        entries = [(Address(1, 1, 1, i % 256), i % MAX_ROUTE_HOPS) for i in range(MAX_ROUTE_ENTRIES)]
        payload = _pack_route_entries(entries)
        self.assertLessEqual(len(payload), 256)


class TestRouteLearning(unittest.TestCase):
    def test_direct_neighbor_learned_at_hop_one(self):
        sim = Simulator()
        sim.log_events = False
        plc = Medium("plc", bitrate_bps=4800, rng=random.Random(1))
        a = _node(sim, "01.01.01.01", plc, 1)
        b = _node(sim, "01.01.01.02", plc, 2)

        sim.run(ROUTE_ADVERTISE_INTERVAL + 5)

        self.assertIn(b.address, a.routing_table)
        self.assertEqual(a.routing_table[b.address].hop_count, 1)
        self.assertEqual(a.routing_table[b.address].next_hop, b.address)
        self.assertIn(a.address, b.routing_table)
        self.assertEqual(b.routing_table[a.address].hop_count, 1)

    def test_multihop_chain_converges_with_correct_next_hop(self):
        """A -- seg1 -- B -- seg2 -- C -- seg3 -- D. Full convergence needs
        one advertisement round per hop, since each round only propagates
        one hop further (classic distance-vector behavior)."""
        sim = Simulator()
        sim.log_events = False
        seg1 = Medium("seg1", bitrate_bps=4800, rng=random.Random(1))
        seg2 = Medium("seg2", bitrate_bps=4800, rng=random.Random(2))
        seg3 = Medium("seg3", bitrate_bps=4800, rng=random.Random(3))

        a = _node(sim, "01.01.01.01", seg1, 1)
        b = _node(sim, "01.01.01.02", seg1, 2)
        b.attach_wifi(seg2)
        c = _node(sim, "01.01.01.03", seg2, 3)
        c.attach_wifi(seg3)
        d = _node(sim, "01.01.01.04", seg3, 4)

        sim.run(ROUTE_ADVERTISE_INTERVAL * 4)

        self.assertEqual(a.routing_table[d.address].hop_count, 3)
        self.assertEqual(a.routing_table[d.address].next_hop, b.address)
        self.assertEqual(a.routing_table[c.address].hop_count, 2)

        self.assertEqual(d.routing_table[a.address].hop_count, 3)
        self.assertEqual(d.routing_table[a.address].next_hop, c.address)

    def test_self_referencing_entry_is_discarded(self):
        """A neighbor re-advertising a route that points back at me must not
        be recorded — the only loop suppression this simplified distance
        vector scheme relies on."""
        sim = Simulator()
        sim.log_events = False
        plc = Medium("plc", bitrate_bps=4800, rng=random.Random(1))
        a = _node(sim, "01.01.01.01", plc, 1)
        b_addr = Address.parse("01.01.01.02")

        payload = _pack_route_entries([(a.address, 1)])  # B claims "A is 1 hop via me"
        pkt = Packet(src=b_addr, dst=Address(0xFF, 0xFF, 0xFF, 0xFF), seq=1, type=MessageType.ROUTE, payload=payload)
        a._on_receive_raw(pkt.encode(), plc)

        self.assertNotIn(a.address, a.routing_table)

    def test_worse_route_from_current_next_hop_is_still_accepted(self):
        """If topology changes and our current next_hop's own path gets
        longer, we must accept the update even though it's worse — otherwise
        we'd keep routing toward a path that no longer exists at that length."""
        sim = Simulator()
        sim.log_events = False
        plc = Medium("plc", bitrate_bps=4800, rng=random.Random(1))
        a = _node(sim, "01.01.01.01", plc, 1)
        neighbor = Address.parse("01.01.01.02")
        far = Address.parse("01.01.01.09")

        good = Packet(
            src=neighbor, dst=Address(0xFF, 0xFF, 0xFF, 0xFF), seq=1,
            type=MessageType.ROUTE, payload=_pack_route_entries([(far, 1)]),
        )
        a._on_receive_raw(good.encode(), plc)
        self.assertEqual(a.routing_table[far].hop_count, 2)

        worse = Packet(
            src=neighbor, dst=Address(0xFF, 0xFF, 0xFF, 0xFF), seq=2,
            type=MessageType.ROUTE, payload=_pack_route_entries([(far, 5)]),
        )
        a._on_receive_raw(worse.encode(), plc)
        self.assertEqual(a.routing_table[far].hop_count, 6)

    def test_hop_count_capped_at_infinity(self):
        sim = Simulator()
        sim.log_events = False
        plc = Medium("plc", bitrate_bps=4800, rng=random.Random(1))
        a = _node(sim, "01.01.01.01", plc, 1)
        neighbor = Address.parse("01.01.01.02")
        far = Address.parse("01.01.01.09")

        pkt = Packet(
            src=neighbor, dst=Address(0xFF, 0xFF, 0xFF, 0xFF), seq=1,
            type=MessageType.ROUTE, payload=_pack_route_entries([(far, MAX_ROUTE_HOPS - 1)]),
        )
        a._on_receive_raw(pkt.encode(), plc)

        self.assertNotIn(far, a.routing_table)  # MAX_ROUTE_HOPS - 1 + 1 == MAX_ROUTE_HOPS: dropped, not propagated

    def test_stale_route_excluded_from_next_advertisement(self):
        sim = Simulator()
        sim.log_events = False
        plc = Medium("plc", bitrate_bps=4800, rng=random.Random(1))
        a = _node(sim, "01.01.01.01", plc, 1)
        far = Address.parse("01.01.01.09")

        pkt = Packet(
            src=Address.parse("01.01.01.02"), dst=Address(0xFF, 0xFF, 0xFF, 0xFF), seq=1,
            type=MessageType.ROUTE, payload=_pack_route_entries([(far, 0)]),
        )
        a._on_receive_raw(pkt.encode(), plc)
        self.assertIn(far, dict(a._active_routes()))

        sim.run(sim.now + ROUTE_STALE + 1)  # no refresh arrives — entry goes stale
        self.assertNotIn(far, dict(a._active_routes()))


if __name__ == "__main__":
    unittest.main()
