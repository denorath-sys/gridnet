import unittest

from forth_vm.gridnet import (
    BROADCAST_ADDR,
    MAX_MESSAGE_SIZE,
    RATE_LIMIT_MAX,
    RATE_LIMIT_WINDOW,
    GridnetVM,
    SandboxViolation,
)
from forth_vm.vm import ForthError


class TestScreen(unittest.TestCase):
    def test_write_places_text_at_row_col(self):
        vm = GridnetVM()
        vm.run('0 0 S" hello" WRITE')
        self.assertTrue(vm.screen.render().splitlines()[0].startswith("hello"))

    def test_write_at_nonzero_row_leaves_earlier_rows_blank(self):
        vm = GridnetVM()
        vm.run('5 2 S" hi" WRITE')
        lines = vm.screen.render().splitlines()
        self.assertEqual(lines[0], "")
        self.assertEqual(lines[1], "")
        self.assertTrue(lines[2].startswith("     hi"))  # 5 leading spaces

    def test_write_clips_past_right_edge_instead_of_wrapping_or_erroring(self):
        vm = GridnetVM()
        vm.run(f'75 0 S" {"X" * 20}" WRITE')  # would run off the 80-column edge
        line = vm.screen.render().splitlines()[0]
        self.assertEqual(len(line), 80)
        self.assertTrue(line.endswith("X" * 5))

    def test_write_below_bottom_row_is_silently_ignored(self):
        vm = GridnetVM()
        vm.run('0 999 S" off screen" WRITE')  # should not raise, not appear anywhere
        self.assertNotIn("off screen", vm.screen.render())

    def test_page_clears_the_screen(self):
        vm = GridnetVM()
        vm.run('0 0 S" hello" WRITE PAGE')
        self.assertEqual(vm.screen.render().strip(), "")  # 25 blank rows, still newline-joined


class TestKeyboard(unittest.TestCase):
    def test_key_query_reflects_queue_state(self):
        vm = GridnetVM()
        vm.run("KEY? .")
        self.assertEqual(vm.output, "0")  # FALSE — nothing queued
        vm.clear_output()
        vm.feed_keys("1")
        vm.run("KEY? .")
        self.assertEqual(vm.output, "-1")  # TRUE

    def test_key_pops_in_order_and_drains_the_queue(self):
        vm = GridnetVM()
        vm.feed_keys("12")
        vm.run("KEY . KEY . KEY? .")
        self.assertEqual(vm.output, str(ord("1")) + str(ord("2")) + "0")

    def test_key_with_empty_queue_raises(self):
        vm = GridnetVM()
        with self.assertRaises(ForthError):
            vm.run("KEY")


class TestSendMsgSandbox(unittest.TestCase):
    def test_successful_send_recorded_with_locked_source_address(self):
        vm = GridnetVM(address="01.03.07.11")
        vm.run('S" order: bread" S" 01.03.07.12" SEND-MSG')
        self.assertEqual(len(vm.outbox), 1)
        sent = vm.outbox[0]
        self.assertEqual(sent.src, "01.03.07.11")
        self.assertEqual(sent.dst, "01.03.07.12")
        self.assertEqual(sent.payload, "order: bread")

    def test_no_word_exists_to_change_the_source_address(self):
        # "Address lock" is enforced by omission: there's simply no builtin
        # that writes to vm.address, so a sandboxed app cannot spoof it.
        vm = GridnetVM(address="01.03.07.11")
        self.assertNotIn("ADDRESS!", vm.dictionary)
        self.assertNotIn("SRC!", vm.dictionary)
        vm.run(': TRY-EVERYTHING 1 2 3 DROP DROP DROP ; TRY-EVERYTHING')
        self.assertEqual(vm.address, "01.03.07.11")

    def test_oversized_payload_rejected(self):
        vm = GridnetVM()
        with self.assertRaises(SandboxViolation):
            vm._do_send("x" * (MAX_MESSAGE_SIZE + 1), "01.03.07.12")
        self.assertEqual(vm.outbox, [])

    def test_payload_at_exactly_the_limit_is_accepted(self):
        vm = GridnetVM()
        vm._do_send("x" * MAX_MESSAGE_SIZE, "01.03.07.12")
        self.assertEqual(len(vm.outbox), 1)

    def test_int_payload_accepted_as_a_single_byte(self):
        # e.g. sending a raw KEY result without converting it to text first
        vm = GridnetVM()
        vm._do_send(ord("1"), "01.03.07.12")
        self.assertEqual(vm.outbox[0].payload, ord("1"))

    def test_unsupported_payload_type_rejected(self):
        vm = GridnetVM()
        with self.assertRaises(SandboxViolation):
            vm._do_send([1, 2, 3], "01.03.07.12")

    def test_broadcast_without_permission_rejected(self):
        vm = GridnetVM(allow_broadcast=False)
        with self.assertRaises(SandboxViolation):
            vm.run(f'S" hi all" S" {BROADCAST_ADDR}" SEND-MSG')

    def test_broadcast_word_and_permission_together_succeed(self):
        vm = GridnetVM(allow_broadcast=True)
        vm.run('S" hi all" BROADCAST SEND-MSG')
        self.assertEqual(vm.outbox[0].dst, BROADCAST_ADDR)

    def test_rate_limit_enforced_within_the_window(self):
        vm = GridnetVM()
        for _ in range(RATE_LIMIT_MAX):
            vm._do_send("msg", "01.03.07.12")
        with self.assertRaises(SandboxViolation):
            vm._do_send("one too many", "01.03.07.12")
        self.assertEqual(len(vm.outbox), RATE_LIMIT_MAX)

    def test_rate_limit_window_clears_after_wait(self):
        vm = GridnetVM()
        for _ in range(RATE_LIMIT_MAX):
            vm._do_send("msg", "01.03.07.12")
        vm.now += RATE_LIMIT_WINDOW + 0.1
        vm._do_send("after the window", "01.03.07.12")  # should not raise
        self.assertEqual(len(vm.outbox), RATE_LIMIT_MAX + 1)

    def test_wait_word_advances_virtual_clock_not_real_time(self):
        vm = GridnetVM()
        vm.run("1500 WAIT")
        self.assertEqual(vm.now, 1.5)


class TestCornerShopIntegration(unittest.TestCase):
    """End-to-end: the actual top-level README's corner-shop idea, adapted to
    use real KEY?/KEY (the README's one-liner `KEY? SEND-MSG` was
    illustrative pseudocode — KEY? is a boolean check in real Forth, so the
    working equivalent checks it, then reads the key, then sends)."""

    def test_menu_selection_gets_sent_once_a_key_is_available(self):
        vm = GridnetVM(address="01.03.07.11")
        vm.run("""
            : HEADER
                0 0 S" +---------------+" WRITE
                0 1 S" |  CORNER SHOP  |" WRITE
                0 2 S" +---------------+" WRITE ;
            : ORDER
                HEADER
                0 4 S" 1. Bread  2. Milk" WRITE
                KEY? IF KEY S" 01.03.07.99" SEND-MSG THEN ;
        """)
        vm.run("ORDER")  # no key queued yet — should do nothing
        self.assertEqual(vm.outbox, [])

        vm.feed_keys("1")
        vm.run("ORDER")
        self.assertEqual(len(vm.outbox), 1)
        self.assertEqual(vm.outbox[0].payload, ord("1"))
        self.assertIn("CORNER SHOP", vm.screen.render())


if __name__ == "__main__":
    unittest.main()
