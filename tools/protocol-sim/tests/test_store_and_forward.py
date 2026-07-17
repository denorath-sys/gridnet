import random
import unittest

from gridnet_sim.address import Address
from gridnet_sim.medium import Medium
from gridnet_sim.node import OUTBOX_EXPIRY, OUTBOX_RETRY_INTERVAL, Node
from gridnet_sim.simulator import Simulator


class TestStoreAndForward(unittest.TestCase):
    def test_message_queued_while_destination_unreachable(self):
        sim = Simulator()
        sim.log_events = False
        plc = Medium("plc", bitrate_bps=4800, rng=random.Random(42))
        a = Node(sim, Address.parse("01.01.01.01"), plc_medium=plc)

        a.send_message(Address.parse("01.01.01.02"), b"anyone there?")
        sim.run(OUTBOX_RETRY_INTERVAL * 2 + 1)

        self.assertEqual(len(a.outbox), 1)
        self.assertGreaterEqual(a.outbox[0].attempts, 2)

    def test_delivered_once_destination_joins(self):
        sim = Simulator()
        sim.log_events = False
        plc = Medium("plc", bitrate_bps=4800, rng=random.Random(42))
        a = Node(sim, Address.parse("01.01.01.01"), plc_medium=plc)
        b_addr = Address.parse("01.01.01.02")

        a.send_message(b_addr, b"anyone there?")
        sim.run(OUTBOX_RETRY_INTERVAL + 1)  # one failed attempt already happened
        self.assertEqual(len(a.outbox), 1)

        b = Node(sim, b_addr, plc_medium=plc)
        sim.run(sim.now + OUTBOX_RETRY_INTERVAL + 5)  # wait for the next retry to find b

        self.assertEqual(a.outbox, [])
        self.assertEqual(len(b.inbox), 1)
        self.assertEqual(b.inbox[0].payload, b"anyone there?")

    def test_ack_clears_outbox_immediately_without_waiting_for_retry(self):
        sim = Simulator()
        sim.log_events = False
        plc = Medium("plc", bitrate_bps=4800, rng=random.Random(42))
        a = Node(sim, Address.parse("01.01.01.01"), plc_medium=plc)
        b = Node(sim, Address.parse("01.01.01.02"), plc_medium=plc)

        a.send_message(b.address, b"hi")
        sim.run(1)  # well under the retry interval

        self.assertEqual(a.outbox, [])
        self.assertEqual(len(b.inbox), 1)

    def test_undelivered_message_expires_after_seven_days(self):
        sim = Simulator()
        sim.log_events = False
        plc = Medium("plc", bitrate_bps=4800, rng=random.Random(42))
        a = Node(sim, Address.parse("01.01.01.01"), plc_medium=plc)

        a.send_message(Address.parse("01.01.01.02"), b"never delivered")
        sim.run(OUTBOX_EXPIRY - 1)
        self.assertEqual(len(a.outbox), 1)  # not expired yet

        sim.run(OUTBOX_EXPIRY + OUTBOX_RETRY_INTERVAL + 1)
        self.assertEqual(a.outbox, [])  # expired and dropped


if __name__ == "__main__":
    unittest.main()
