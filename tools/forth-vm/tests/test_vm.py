import unittest

from forth_vm.vm import ForthError, ForthVM, StepLimitExceeded, tokenize


def run(src: str) -> str:
    vm = ForthVM()
    vm.run(src)
    return vm.output


class TestTokenizer(unittest.TestCase):
    def test_words_split_on_whitespace(self):
        toks = list(tokenize("1 2 +"))
        self.assertEqual(toks, [("WORD", "1"), ("WORD", "2"), ("WORD", "+")])

    def test_paren_comment_is_skipped(self):
        toks = list(tokenize("1 ( this is a comment ) 2 +"))
        self.assertEqual(toks, [("WORD", "1"), ("WORD", "2"), ("WORD", "+")])

    def test_backslash_line_comment_is_skipped(self):
        toks = list(tokenize("1 2 + \\ rest of line ignored\n3"))
        self.assertEqual(toks, [("WORD", "1"), ("WORD", "2"), ("WORD", "+"), ("WORD", "3")])

    def test_string_literal_excludes_delimiter_space(self):
        toks = list(tokenize('." hello world"'))
        self.assertEqual(toks, [("STR", "hello world")])

    def test_unterminated_string_raises(self):
        with self.assertRaises(ForthError):
            list(tokenize('." unterminated'))

    def test_unterminated_comment_raises(self):
        with self.assertRaises(ForthError):
            list(tokenize("1 ( unterminated"))


class TestArithmetic(unittest.TestCase):
    def test_add_sub_mul(self):
        self.assertEqual(run("2 3 + ."), "5")
        self.assertEqual(run("10 4 - ."), "6")
        self.assertEqual(run("6 7 * ."), "42")

    def test_floor_division_and_mod(self):
        self.assertEqual(run("7 2 / ."), "3")
        self.assertEqual(run("7 2 MOD ."), "1")
        self.assertEqual(run("-7 2 / ."), "-4")  # floor division, not truncation
        self.assertEqual(run("-7 2 MOD ."), "1")

    def test_negate(self):
        self.assertEqual(run("5 NEGATE ."), "-5")


class TestComparisonAndLogic(unittest.TestCase):
    def test_equality_uses_ans_forth_booleans(self):
        self.assertEqual(run("5 5 = ."), "-1")  # TRUE is -1
        self.assertEqual(run("5 4 = ."), "0")  # FALSE is 0

    def test_ordering(self):
        self.assertEqual(run("3 5 < ."), "-1")
        self.assertEqual(run("5 3 < ."), "0")
        self.assertEqual(run("5 3 > ."), "-1")
        self.assertEqual(run("3 5 <= ."), "-1")
        self.assertEqual(run("5 5 >= ."), "-1")
        self.assertEqual(run("3 5 <> ."), "-1")

    def test_bitwise_and_or_xor_invert(self):
        self.assertEqual(run("6 3 AND ."), "2")
        self.assertEqual(run("6 3 OR ."), "7")
        self.assertEqual(run("6 3 XOR ."), "5")
        self.assertEqual(run("0 INVERT ."), "-1")


class TestStackOps(unittest.TestCase):
    def test_dup_drop_swap_over_rot(self):
        self.assertEqual(run("5 DUP + ."), "10")
        self.assertEqual(run("1 2 DROP ."), "1")
        self.assertEqual(run("1 2 SWAP - ."), "1")  # 2 1 -> 1
        self.assertEqual(run("1 2 OVER . . ."), "121")  # stack becomes 1 2 1, printed top-first
        self.assertEqual(run("1 2 3 ROT . . ."), "132")  # 2 3 1 -> prints 1,3,2

    def test_stack_underflow_raises(self):
        with self.assertRaises(ForthError):
            run("DUP")
        with self.assertRaises(ForthError):
            run("+")


class TestControlFlow(unittest.TestCase):
    def test_if_then(self):
        self.assertEqual(run(": T 0 > IF 111 . THEN ; 5 T"), "111")
        self.assertEqual(run(": T 0 > IF 111 . THEN ; -5 T"), "")

    def test_if_else_then(self):
        src = ": ABS DUP 0 < IF NEGATE THEN ; -5 ABS . 5 ABS ."
        self.assertEqual(run(src), "55")

    def test_nested_if(self):
        src = """
        : CLASSIFY
            DUP 0 = IF ." zero"
            ELSE DUP 0 < IF ." negative"
            ELSE ." positive" THEN THEN DROP ;
        -1 CLASSIFY 0 CLASSIFY 1 CLASSIFY
        """
        self.assertEqual(run(src), "negativezeropositive")

    def test_begin_until(self):
        src = ": COUNTDOWN BEGIN DUP . 1 - DUP 0 = UNTIL DROP ; 3 COUNTDOWN"
        self.assertEqual(run(src), "321")

    def test_begin_while_repeat(self):
        src = ": UPTO3 0 BEGIN DUP 3 < WHILE DUP . 1 + REPEAT DROP ; UPTO3"
        self.assertEqual(run(src), "012")

    def test_begin_again_is_unconditional_and_needs_a_step_limit_to_stop(self):
        vm = ForthVM(step_limit=25)
        with self.assertRaises(StepLimitExceeded):
            vm.run(": SPIN 0 BEGIN 1 + DUP . AGAIN ; SPIN")
        self.assertTrue(vm.output.startswith("123"))  # it did run, just never terminates on its own

    def test_step_limit_none_by_default_does_not_affect_normal_programs(self):
        # A large but finite DO loop must run to completion when no
        # step_limit is set — confirms the safety valve is opt-in.
        self.assertEqual(run(": BIG 200 0 DO I DROP LOOP ; BIG 111 ."), "111")

    def test_do_loop_with_index(self):
        self.assertEqual(run(": COUNT 5 0 DO I . LOOP ; COUNT"), "01234")

    def test_nested_do_loop(self):
        src = ": GRID 3 0 DO 3 0 DO I . LOOP LOOP ; GRID"
        self.assertEqual(run(src), "012012012")

    def test_recursion(self):
        src = ": FACT DUP 1 <= IF DROP 1 ELSE DUP 1 - FACT * THEN ; 5 FACT ."
        self.assertEqual(run(src), "120")

    def test_control_word_outside_definition_rejected(self):
        for src in ("THEN", "LOOP", "UNTIL", "REPEAT", "ELSE"):
            with self.assertRaises(ForthError):
                run(src)

    def test_unbalanced_control_flow_rejected(self):
        with self.assertRaises(ForthError):
            run(": X IF ; X")
        with self.assertRaises(ForthError):
            run(": X 1 +")  # missing ;


class TestDefinitions(unittest.TestCase):
    def test_variable_and_fetch_store(self):
        src = "VARIABLE X  5 X !  X @ .  X @ 1 + X !  X @ ."
        self.assertEqual(run(src), "56")

    def test_multiple_variables_have_independent_storage(self):
        src = "VARIABLE X  VARIABLE Y  1 X !  2 Y !  X @ .  Y @ ."
        self.assertEqual(run(src), "12")

    def test_constant(self):
        self.assertEqual(run("42 CONSTANT ANSWER ANSWER ."), "42")

    def test_redefinition_uses_latest_definition(self):
        # Documented simplification: word calls resolve by name at execution
        # time, so redefining DOUBLE after TEST was compiled still affects it.
        src = ": DOUBLE 2 * ; : TEST 5 DOUBLE ; : DOUBLE 3 * ; TEST ."
        self.assertEqual(run(src), "15")

    def test_nested_colon_definition_rejected(self):
        with self.assertRaises(ForthError):
            run(": A : B ; ;")

    def test_variable_inside_definition_rejected(self):
        with self.assertRaises(ForthError):
            run(": A VARIABLE X ;")


class TestOutput(unittest.TestCase):
    def test_dot_prints_number(self):
        self.assertEqual(run("42 ."), "42")

    def test_emit_prints_char(self):
        self.assertEqual(run("65 EMIT"), "A")

    def test_cr_prints_newline(self):
        self.assertEqual(run("1 . CR 2 ."), "1\n2")

    def test_string_literal_interpret_mode(self):
        self.assertEqual(run('." direct output"'), "direct output")

    def test_s_quote_pushes_a_string_value_instead_of_printing(self):
        vm = ForthVM()
        vm.run('S" pushed"')
        self.assertEqual(vm.stack, ["pushed"])
        self.assertEqual(vm.output, "")  # unlike .", nothing is printed

    def test_s_quote_value_can_be_printed_later(self):
        self.assertEqual(run('S" hi" DUP . CR'), "hi\n")

    def test_s_quote_works_inside_a_definition(self):
        vm = ForthVM()
        vm.run(': GET-GREETING S" hello" ; GET-GREETING')
        self.assertEqual(vm.stack, ["hello"])


class TestErrors(unittest.TestCase):
    def test_unknown_word_message(self):
        with self.assertRaisesRegex(ForthError, r"\? FOOBAR"):
            run("FOOBAR")

    def test_loop_index_outside_do_rejected(self):
        with self.assertRaises(ForthError):
            run("I .")


if __name__ == "__main__":
    unittest.main()
