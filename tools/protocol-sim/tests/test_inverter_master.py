import random
import unittest

from gridnet_sim.address import Address
from gridnet_sim.medium import Medium
from gridnet_sim.node import (
    FAILOVER_GRACE_PERIOD,
    JOIN_LISTEN_DELAY,
    LISTEN_DELAY,
    LISTEN_JITTER,
    MASTER_ALIVE_INTERVAL,
    MASTER_TIMEOUT,
    InverterState,
    Node,
)
from gridnet_sim.simulator import Simulator

# Larger than LISTEN_JITTER's spread, so a manual stagger of this size always
# dominates the random jitter and keeps ordering deterministic in tests that
# care which specific node wins.
STAGGER = 0.6


def _segment(n=3, addrs=None):
    sim = Simulator()
    sim.log_events = False
    plc = Medium("plc", bitrate_bps=4800, rng=random.Random(42))
    addrs = addrs or [f"01.03.07.{i}" for i in (11, 12, 13)][:n]
    nodes = [Node(sim, Address.parse(a), plc_medium=plc) for a in addrs]
    return sim, nodes


class TestMasterElection(unittest.TestCase):
    def test_lowest_address_becomes_master_when_staggered(self):
        sim, nodes = _segment()
        for i, node in enumerate(nodes):
            sim.schedule(i * STAGGER, node.grid_lost)
        sim.run(2 * STAGGER + LISTEN_DELAY + LISTEN_JITTER + 1)

        master, slave1, slave2 = nodes
        self.assertEqual(master.inverter_state, InverterState.INV_MASTER)
        self.assertEqual(slave1.inverter_state, InverterState.INV_SLAVE)
        self.assertEqual(slave2.inverter_state, InverterState.INV_SLAVE)
        self.assertEqual(slave1.master_addr, master.address)
        self.assertEqual(slave2.master_addr, master.address)

    def test_simultaneous_grid_loss_no_longer_reliably_collides(self):
        """The fix: with jittered listen delays, three nodes losing grid power
        at the exact same instant should usually converge on one master
        directly (the fastest jitter draw asserts, the others hear it and
        become slaves) instead of every single run needing split-brain to
        sort it out. This isn't a hard guarantee for every possible jitter
        draw — see test_split_brain_still_resolves_ties below for the residual
        case — but it must hold for typical, unseeded random jitter, so we
        sample many independent runs and require the large majority to
        avoid any split-brain messaging."""
        split_brain_count = 0
        trials = 30
        for seed in range(trials):
            sim = Simulator()
            sim.log_events = False
            plc = Medium("plc", bitrate_bps=4800, rng=random.Random(seed))
            nodes = [
                Node(sim, Address.parse(f"01.03.07.{i}"), plc_medium=plc, rng=random.Random(seed * 100 + i))
                for i in (11, 12, 13)
            ]
            for node in nodes:
                node.grid_lost()
            sim.run(LISTEN_DELAY + LISTEN_JITTER + 2)

            if any("split-brain" in line for line in sim.history):
                split_brain_count += 1

            masters = [n for n in nodes if n.inverter_state == InverterState.INV_MASTER]
            self.assertEqual(len(masters), 1, f"seed={seed}: expected exactly one master")

        self.assertLess(
            split_brain_count / trials,
            0.2,
            f"split-brain triggered in {split_brain_count}/{trials} runs — jitter isn't doing its job",
        )

    def test_split_brain_still_resolves_ties(self):
        """Safety net: if jitter draws genuinely tie (three fresh Random(99)
        instances, each used exactly once, draw the identical value), all
        three still assert simultaneously — split-brain detection must still
        converge on the lowest address, same as REV 0.4."""
        sim, nodes = _segment()
        for node in nodes:
            node._rng = random.Random(99)  # force an exact jitter tie
        for node in nodes:
            node.grid_lost()
        sim.run(LISTEN_DELAY + LISTEN_JITTER + 2)

        addresses = sorted(n.address for n in nodes)
        lowest = next(n for n in nodes if n.address == addresses[0])
        others = [n for n in nodes if n is not lowest]

        self.assertEqual(lowest.inverter_state, InverterState.INV_MASTER)
        for other in others:
            self.assertEqual(other.inverter_state, InverterState.INV_SLAVE)
            self.assertEqual(other.master_addr, lowest.address)


class TestColdJoin(unittest.TestCase):
    """cold_join() is for a device powering on / rejoining while the grid is
    already off — it can't assume no master exists, so it needs a listen
    window that reliably spans a full MASTER_ALIVE cycle (see grid_lost()
    and cold_join() docstrings in gridnet_sim/node.py)."""

    def test_reliably_hears_existing_master_regardless_of_join_timing(self):
        for join_offset in (0.1, 3.0, 6.0, 9.9):
            with self.subTest(join_offset=join_offset):
                sim, nodes = _segment(n=2, addrs=["01.03.07.11", "01.03.07.12"])
                nodes[0].grid_lost()
                sim.run(LISTEN_DELAY + LISTEN_JITTER + 1)  # master established, heartbeats at ~2, 12, 22...
                self.assertEqual(nodes[0].inverter_state, InverterState.INV_MASTER)

                newcomer = Node(sim, Address.parse("01.03.07.05"), plc_medium=nodes[0].plc_medium)
                sim.schedule(join_offset, newcomer.cold_join)
                sim.run(sim.now + join_offset + JOIN_LISTEN_DELAY + LISTEN_JITTER + 1)

                self.assertEqual(newcomer.inverter_state, InverterState.INV_SLAVE)
                self.assertEqual(newcomer.master_addr, nodes[0].address)

    def test_grid_lost_is_the_wrong_call_for_joining_an_existing_segment(self):
        """API-contract regression guard: grid_lost() assumes no master could
        already exist, so using it (instead of cold_join()) to join an
        already-running segment reproduces the original REV 0.4 bug — a
        misuse case, not evidence the fix regressed."""
        sim, nodes = _segment(n=2, addrs=["01.03.07.11", "01.03.07.12"])
        nodes[0].grid_lost()
        sim.run(LISTEN_DELAY + LISTEN_JITTER + 1)  # master established, heartbeats at ~2, 12, 22...
        self.assertEqual(nodes[0].inverter_state, InverterState.INV_MASTER)

        newcomer = Node(sim, Address.parse("01.03.07.05"), plc_medium=nodes[0].plc_medium)
        newcomer.grid_lost()  # wrong call for a join — window falls between heartbeats
        sim.run(sim.now + LISTEN_DELAY + LISTEN_JITTER + 1)

        self.assertEqual(newcomer.inverter_state, InverterState.INV_MASTER)
        self.assertEqual(nodes[0].inverter_state, InverterState.INV_SLAVE)


class TestMasterFailover(unittest.TestCase):
    def test_slave_takes_over_after_master_goes_silent(self):
        sim, nodes = _segment()
        for i, node in enumerate(nodes):
            sim.schedule(i * STAGGER, node.grid_lost)
        sim.run(2 * STAGGER + LISTEN_DELAY + LISTEN_JITTER + 1)

        master, backup, other = nodes
        self.assertEqual(master.inverter_state, InverterState.INV_MASTER)

        master.plc_medium.detach(master.id)  # simulated dead battery — stops hearing/sending
        sim.run(sim.now + MASTER_TIMEOUT + FAILOVER_GRACE_PERIOD + 2)

        self.assertEqual(backup.inverter_state, InverterState.INV_MASTER)
        self.assertEqual(other.inverter_state, InverterState.INV_SLAVE)
        self.assertEqual(other.master_addr, backup.address)

    def test_grid_restored_master_resigns_and_stops_heartbeat(self):
        sim, nodes = _segment(n=2, addrs=["01.03.07.11", "01.03.07.12"])
        for i, node in enumerate(nodes):
            sim.schedule(i * STAGGER, node.grid_lost)
        sim.run(STAGGER + LISTEN_DELAY + LISTEN_JITTER + 1)

        master, slave = nodes
        self.assertEqual(master.inverter_state, InverterState.INV_MASTER)

        master.grid_restored()
        sim.run(sim.now + MASTER_ALIVE_INTERVAL + 1)
        self.assertEqual(master.inverter_state, InverterState.GRID_ON)

        # the slave should have failed over (heard MASTER_RESIGN) rather than
        # waiting out a full 30s timeout with no heartbeat
        sim.run(sim.now + FAILOVER_GRACE_PERIOD + 1)
        self.assertEqual(slave.inverter_state, InverterState.INV_MASTER)
        self.assertLess(sim.now, MASTER_TIMEOUT)  # resign path is much faster than a timeout


if __name__ == "__main__":
    unittest.main()
