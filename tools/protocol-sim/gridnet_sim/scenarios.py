"""Runnable demonstrations of the behaviors described in docs/protocol.md and
docs/inverter-master.md. Each function builds a small network, drives it, and
returns the (sim, nodes) so a caller (run_demo.py or a test) can inspect the
outcome.
"""

from __future__ import annotations

import random

from .address import Address
from .medium import Medium
from .node import JOIN_LISTEN_DELAY, LISTEN_DELAY, LISTEN_JITTER, ROUTE_ADVERTISE_INTERVAL, InverterState, Node
from .simulator import Simulator

# Larger than LISTEN_JITTER's spread, so a manual stagger of this size always
# dominates the random jitter and keeps demo output reproducible.
STAGGER = 0.6


def scenario_basic_exchange():
    """Two nodes, one PLC segment: A sends a message, B ACKs it."""
    sim = Simulator()
    plc = Medium("plc-segment", bitrate_bps=4800)
    a = Node(sim, Address.parse("01.03.07.11"), plc_medium=plc)
    b = Node(sim, Address.parse("01.03.07.12"), plc_medium=plc)

    a.send_message(b.address, b"corner shop: 2x bread, 1x milk")
    sim.run(5)
    return sim, {"a": a, "b": b}


def scenario_multihop_flood():
    """A and C don't share a medium — only the relay does — so the message
    only reaches C if flooding + repeat-once actually works."""
    sim = Simulator()
    seg_a = Medium("plc-seg-a", bitrate_bps=4800)
    seg_c = Medium("plc-seg-c", bitrate_bps=4800)

    a = Node(sim, Address.parse("01.03.07.11"), plc_medium=seg_a)
    relay = Node(sim, Address.parse("01.03.07.12"), plc_medium=seg_a)
    relay.attach_wifi(seg_c)
    c = Node(sim, Address.parse("01.03.08.01"), plc_medium=seg_c)

    a.send_message(c.address, b"is the shop open today?")
    sim.run(10)
    return sim, {"a": a, "relay": relay, "c": c}


def scenario_routing():
    """A -- seg1 -- B -- seg2 -- C -- seg3 -- D, a 4-node/3-hop chain. ROUTE
    is a distance-vector protocol (docs/protocol.md REV 0.5): each
    advertisement round only propagates one hop further, so full end-to-end
    convergence (A learning D is 3 hops away, via B) takes several rounds —
    watch the "learned route" / "updated route" log lines tighten each
    ROUTE_ADVERTISE_INTERVAL."""
    sim = Simulator()
    seg1 = Medium("seg1", bitrate_bps=4800)
    seg2 = Medium("seg2", bitrate_bps=4800)
    seg3 = Medium("seg3", bitrate_bps=4800)

    a = Node(sim, Address.parse("01.03.07.11"), plc_medium=seg1)
    b = Node(sim, Address.parse("01.03.07.12"), plc_medium=seg1)
    b.attach_wifi(seg2)
    c = Node(sim, Address.parse("01.03.07.13"), plc_medium=seg2)
    c.attach_wifi(seg3)
    d = Node(sim, Address.parse("01.03.07.14"), plc_medium=seg3)

    sim.run(ROUTE_ADVERTISE_INTERVAL * 4)
    sim.log(f"--- A's routing table: {[(str(k), v.hop_count, str(v.next_hop)) for k, v in a.routing_table.items()]} ---")
    return sim, {"a": a, "b": b, "c": c, "d": d}


def scenario_store_and_forward():
    """A sends to C while C is offline; C joins the segment later and the
    message is delivered on the next periodic retry — not re-sent from
    scratch, the same outbox entry just gets picked up again."""
    sim = Simulator()
    plc = Medium("plc-segment", bitrate_bps=4800)
    a = Node(sim, Address.parse("01.03.07.11"), plc_medium=plc)
    c_addr = Address.parse("01.03.07.13")

    a.send_message(c_addr, b"welcome to the building")
    sim.run(45)  # C is unreachable — message sits in the outbox, gets retried

    c = Node(sim, c_addr, plc_medium=plc)
    sim.run(sim.now + 35)  # wait for the next retry interval to pick it up
    return sim, {"a": a, "c": c}


def scenario_master_election():
    """Three nodes on one segment all lose grid power at once — the realistic
    common case (a whole building's power goes out simultaneously). REV 0.4's
    flat 2s listen delay made every device time out at the identical instant
    and all try to become master together, every single run. REV 0.5 adds
    jitter (LISTEN_JITTER) so the fastest draw usually asserts first and the
    others just hear it — no split-brain needed for the common case. Seeded
    here for a reproducible demo; see scenario_master_election_worst_case for
    the residual tie case split-brain still exists to catch."""
    sim = Simulator()
    plc = Medium("plc-segment", bitrate_bps=4800, rng=random.Random(7))
    nodes = {
        n: Node(sim, Address.parse(f"01.03.07.{n}"), plc_medium=plc, rng=random.Random(int(n)))
        for n in ("11", "12", "13")
    }
    for node in nodes.values():
        node.grid_lost()
    sim.run(LISTEN_DELAY + LISTEN_JITTER + 2)
    return sim, nodes


def scenario_master_election_worst_case():
    """The residual case scenario_master_election's jitter doesn't fully
    remove: three nodes whose jitter draws genuinely tie (here forced, by
    giving all three the exact same fresh RNG seed) still assert
    simultaneously. Split-brain detection is still there as a safety net and
    must still converge on the lowest address, exactly as it did in REV 0.4."""
    sim = Simulator()
    plc = Medium("plc-segment", bitrate_bps=4800)
    nodes = {
        n: Node(sim, Address.parse(f"01.03.07.{n}"), plc_medium=plc, rng=random.Random(99))
        for n in ("11", "12", "13")
    }
    for node in nodes.values():
        node.grid_lost()
    sim.run(LISTEN_DELAY + LISTEN_JITTER + 2)
    return sim, nodes


def scenario_cold_join():
    """.11 is already an established master (heartbeats every 10s). A new
    device (.05 — a lower address!) joins mid-outage using cold_join(),
    whose long listen window reliably spans a full heartbeat cycle. It
    becomes a slave instead of timing out and stealing mastership the way
    grid_lost() would have (see REV 0.4's bug, documented in
    docs/inverter-master.md's Design Notes)."""
    sim = Simulator()
    plc = Medium("plc-segment", bitrate_bps=4800)
    master = Node(sim, Address.parse("01.03.07.11"), plc_medium=plc)
    master.grid_lost()
    sim.run(LISTEN_DELAY + LISTEN_JITTER + 1)

    newcomer = Node(sim, Address.parse("01.03.07.05"), plc_medium=plc)
    sim.schedule(3.0, newcomer.cold_join)  # joins mid-cycle, well between two heartbeats
    sim.run(sim.now + 3.0 + JOIN_LISTEN_DELAY + LISTEN_JITTER + 1)
    return sim, {"master": master, "newcomer": newcomer}


def scenario_master_failover():
    """Staggered listen delays (larger than LISTEN_JITTER's spread, so they
    dominate it) keep .11 reliably becoming master for this demo. It's then
    knocked out (simulating a dead battery) and .12 should take over ~30s
    later."""
    sim = Simulator()
    plc = Medium("plc-segment", bitrate_bps=4800)
    nodes = {
        n: Node(sim, Address.parse(f"01.03.07.{n}"), plc_medium=plc) for n in ("11", "12", "13")
    }
    for i, node in enumerate(nodes.values()):
        sim.schedule(i * STAGGER, node.grid_lost)
    sim.run(2 * STAGGER + LISTEN_DELAY + LISTEN_JITTER + 1)

    master = nodes["11"]
    assert master.inverter_state == InverterState.INV_MASTER
    sim.log(f"--- knocking out {master.address} (simulated dead battery) ---")
    if master.plc_medium is not None:
        master.plc_medium.detach(master.id)

    sim.run(sim.now + 40)
    return sim, nodes


def scenario_channel_fallback():
    """Two nodes have both PLC and WiFi attached. The PLC line gets physically
    damaged mid-conversation — the next message should go out over WiFi mesh
    instead, per the channel priority table in docs/protocol.md."""
    sim = Simulator()
    plc = Medium("plc-segment", bitrate_bps=4800)
    wifi = Medium("wifi-mesh", bitrate_bps=1_000_000, loss_probability=0.0)

    a = Node(sim, Address.parse("01.03.07.11"), plc_medium=plc)
    a.attach_wifi(wifi)
    b = Node(sim, Address.parse("01.03.07.12"), plc_medium=plc)
    b.attach_wifi(wifi)

    a.send_message(b.address, b"over the wire")
    sim.run(2)

    a.line_damaged()
    a.send_message(b.address, b"over the air")
    sim.run(sim.now + 2)
    return sim, {"a": a, "b": b}


SCENARIOS = {
    "basic-exchange": scenario_basic_exchange,
    "multihop-flood": scenario_multihop_flood,
    "routing": scenario_routing,
    "store-and-forward": scenario_store_and_forward,
    "master-election": scenario_master_election,
    "master-election-worst-case": scenario_master_election_worst_case,
    "cold-join": scenario_cold_join,
    "master-failover": scenario_master_failover,
    "channel-fallback": scenario_channel_fallback,
}
