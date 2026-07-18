"""Core Forth interpreter.

Design notes (deviations from a "real" Forth, chosen because this is a
language-semantics prototype, not a from-scratch embedded VM implementation):

- Colon definitions compile to a nested list of ops (e.g. an IF compiles to
  `('IF', true_branch, false_branch)` holding its own sub-lists), not linear
  threaded code with branch/jump offsets. Real Forth (and the eventual
  embedded port) uses the latter for compactness — a flat instruction stream
  is far cheaper on ~2KB RAM than a tree of Python lists. The nested form is
  easier to get right and to test, which matters more here: this prototype's
  job is pinning down word behavior and the sandbox model, not the compiled
  bytecode layout.
- Word calls are resolved by dictionary lookup at *execution* time, not bound
  at *compile* time. Real Forth binds a word to whatever definition of that
  name existed at compile time, so redefining a word later doesn't change
  already-compiled callers. Here, redefinition affects every caller
  immediately. Simpler to implement; matters only if a program redefines a
  word after using it, which the sandboxed app model this is prototyping
  doesn't really do.
- Booleans follow the ANS Forth convention: TRUE is -1 (all bits set), FALSE
  is 0 — not Python's True/False — so AND/OR/XOR/INVERT double as both
  logical and bitwise operators, same as real Forth.
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Tuple, Union

Token = Tuple[str, str]  # ("WORD", text), ("STR", text), or ("STRLIT", text)

TRUE = -1
FALSE = 0

CONTROL_WORDS = {"IF", "ELSE", "THEN", "BEGIN", "UNTIL", "WHILE", "REPEAT", "AGAIN", "DO", "LOOP"}


class ForthError(Exception):
    pass


class StepLimitExceeded(ForthError):
    """Raised when a VM constructed with step_limit=N executes more than N
    ops without finishing — the safety valve a real sandboxed VM needs
    against a runaway BEGIN...AGAIN or buggy loop. docs/firmware-arch.md's
    sandbox table covers rate limiting, message size, filesystem isolation,
    and screen bounds, but nothing about CPU/step budget — this is the gap
    that fills, at the language level (a real embedded VM would likely also
    want a watchdog timer at the RTOS level)."""


def tokenize(text: str) -> Iterator[Token]:
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            return
        if text[i] == "(":
            close = text.find(")", i)
            if close == -1:
                raise ForthError("unterminated ( comment )")
            i = close + 1
            continue
        if text[i] == "\\" and (i + 1 >= n or text[i + 1].isspace()):
            newline = text.find("\n", i)
            i = n if newline == -1 else newline + 1
            continue
        if text[i : i + 2] == '."':
            start = i + 2
            if start < n and text[start] == " ":
                start += 1  # the delimiter space after ." is not part of the string
            close = text.find('"', start)
            if close == -1:
                raise ForthError('unterminated ." string"')
            yield ("STR", text[start:close])
            i = close + 1
            continue
        if text[i : i + 2].upper() == 'S"':
            start = i + 2
            if start < n and text[start] == " ":
                start += 1  # the delimiter space after S" is not part of the string
            close = text.find('"', start)
            if close == -1:
                raise ForthError('unterminated S" string"')
            yield ("STRLIT", text[start:close])
            i = close + 1
            continue
        j = i
        while j < n and not text[j].isspace():
            j += 1
        yield ("WORD", text[i:j])
        i = j


def _parse_number(token: str):
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return None


Op = Union[Tuple[str, ...], object]


class ForthVM:
    def __init__(self, output=None, step_limit: Optional[int] = None) -> None:
        self.stack: List[object] = []
        self.memory: List[object] = []
        self.dictionary: dict = {}
        self.loop_stack: List[int] = []
        self._output = output if output is not None else []
        self.step_limit = step_limit
        self._steps = 0
        self._register_builtins()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def run(self, text: str) -> None:
        tokens = tokenize(text)
        self._interpret(tokens)

    @property
    def output(self) -> str:
        return "".join(self._output)

    def clear_output(self) -> None:
        self._output.clear()

    def pop(self):
        if not self.stack:
            raise ForthError("stack underflow")
        return self.stack.pop()

    def push(self, value) -> None:
        self.stack.append(value)

    # ------------------------------------------------------------------ #
    # Top-level interpreter (handles : ; VARIABLE CONSTANT, then executes)
    # ------------------------------------------------------------------ #

    def _interpret(self, tokens: Iterator[Token]) -> None:
        for kind, text in tokens:
            if kind == "STR":
                self._output.append(text)
                continue
            if kind == "STRLIT":
                self.push(text)
                continue
            word = text.upper()
            if word == ":":
                self._define_word(tokens)
            elif word == "VARIABLE":
                self._define_variable(tokens)
            elif word == "CONSTANT":
                self._define_constant(tokens)
            elif word in CONTROL_WORDS:
                raise ForthError(f"{word} can only be used inside a : definition")
            else:
                self._exec_ops([self._resolve(word)])

    def _next_word(self, tokens: Iterator[Token], context: str) -> str:
        try:
            kind, text = next(tokens)
        except StopIteration:
            raise ForthError(f"unexpected end of input after {context}") from None
        if kind != "WORD":
            raise ForthError(f"expected a name after {context}, got a string literal")
        return text.upper()

    def _define_word(self, tokens: Iterator[Token]) -> None:
        name = self._next_word(tokens, ":")
        body = self._compile_body(tokens, stop_words=(";",))
        if body.stop != ";":
            raise ForthError(f"unterminated : {name} definition (missing ;)")
        self.dictionary[name] = ("WORD", body.ops)

    def _define_variable(self, tokens: Iterator[Token]) -> None:
        name = self._next_word(tokens, "VARIABLE")
        addr = len(self.memory)
        self.memory.append(0)
        self.dictionary[name] = ("BUILTIN", lambda vm, a=addr: vm.push(a))

    def _define_constant(self, tokens: Iterator[Token]) -> None:
        name = self._next_word(tokens, "CONSTANT")
        value = self.pop()
        self.dictionary[name] = ("BUILTIN", lambda vm, v=value: vm.push(v))

    # ------------------------------------------------------------------ #
    # Compiler: token stream -> nested op list, for the body of a : ; word
    # or a control-flow branch/loop body.
    # ------------------------------------------------------------------ #

    class _Body:
        def __init__(self, ops: List[Op], stop: str) -> None:
            self.ops = ops
            self.stop = stop  # which stop-word ended this body

    def _compile_body(self, tokens: Iterator[Token], stop_words: Tuple[str, ...]) -> "_Body":
        ops: List[Op] = []
        for kind, text in tokens:
            if kind == "STR":
                ops.append(("PRINT_STR", text))
                continue
            if kind == "STRLIT":
                ops.append(("LIT", text))
                continue
            word = text.upper()
            if word in stop_words:
                return ForthVM._Body(ops, word)
            if word == "IF":
                ops.append(self._compile_if(tokens))
            elif word == "BEGIN":
                ops.append(self._compile_begin(tokens))
            elif word == "DO":
                body = self._compile_body(tokens, stop_words=("LOOP",))
                ops.append(("DO", body.ops))
            elif word in (";", "ELSE", "THEN", "UNTIL", "WHILE", "REPEAT", "AGAIN", "LOOP"):
                raise ForthError(f"{word} without matching opener")
            elif word == ":":
                raise ForthError(": cannot be nested inside another definition")
            elif word in ("VARIABLE", "CONSTANT"):
                raise ForthError(f"{word} cannot be used inside a : definition")
            else:
                number = _parse_number(word)
                if number is not None:
                    ops.append(("LIT", number))
                else:
                    ops.append(("CALL", word))
        raise ForthError(f"unexpected end of input, expected one of {stop_words}")

    def _compile_if(self, tokens: Iterator[Token]) -> Op:
        true_body = self._compile_body(tokens, stop_words=("ELSE", "THEN"))
        if true_body.stop == "ELSE":
            false_body = self._compile_body(tokens, stop_words=("THEN",))
            return ("IF", true_body.ops, false_body.ops)
        return ("IF", true_body.ops, [])

    def _compile_begin(self, tokens: Iterator[Token]) -> Op:
        first = self._compile_body(tokens, stop_words=("UNTIL", "WHILE", "AGAIN"))
        if first.stop == "UNTIL":
            return ("BEGIN_UNTIL", first.ops)
        if first.stop == "AGAIN":
            return ("BEGIN_AGAIN", first.ops)
        loop_body = self._compile_body(tokens, stop_words=("REPEAT",))
        return ("BEGIN_WHILE", first.ops, loop_body.ops)

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #

    def _resolve(self, word: str) -> Op:
        number = _parse_number(word)
        if number is not None:
            return ("LIT", number)
        return ("CALL", word)

    def _exec_ops(self, ops: List[Op]) -> None:
        for op in ops:
            self._exec_one(op)

    def _exec_one(self, op: Op) -> None:
        if self.step_limit is not None:
            self._steps += 1
            if self._steps > self.step_limit:
                raise StepLimitExceeded(f"exceeded step_limit={self.step_limit} ops")
        kind = op[0]
        if kind == "LIT":
            self.push(op[1])
        elif kind == "PRINT_STR":
            self._output.append(op[1])
        elif kind == "CALL":
            self._call(op[1])
        elif kind == "IF":
            _, true_ops, false_ops = op
            flag = self.pop()
            self._exec_ops(true_ops if flag != FALSE else false_ops)
        elif kind == "BEGIN_UNTIL":
            _, body = op
            while True:
                self._exec_ops(body)
                if self.pop() != FALSE:
                    break
        elif kind == "BEGIN_WHILE":
            _, cond_ops, loop_ops = op
            while True:
                self._exec_ops(cond_ops)
                if self.pop() == FALSE:
                    break
                self._exec_ops(loop_ops)
        elif kind == "BEGIN_AGAIN":
            # Unconditional — no flag popped, unlike UNTIL/WHILE. Only ever
            # terminates via an exception (step_limit, or a builtin raising
            # one) — there's no EXIT/QUIT word in this prototype to break out
            # from Forth code itself, same as real hardware relying on reset.
            _, body = op
            while True:
                self._exec_ops(body)
        elif kind == "DO":
            _, body = op
            start = self.pop()
            limit = self.pop()
            index = start
            while index < limit:
                self.loop_stack.append(index)
                try:
                    self._exec_ops(body)
                finally:
                    self.loop_stack.pop()
                index += 1
        else:
            raise ForthError(f"internal error: unknown op {op!r}")

    def _call(self, word: str) -> None:
        entry = self.dictionary.get(word)
        if entry is None:
            raise ForthError(f"? {word}")
        tag, payload = entry
        if tag == "BUILTIN":
            payload(self)
        else:
            self._exec_ops(payload)

    # ------------------------------------------------------------------ #
    # Builtins
    # ------------------------------------------------------------------ #

    def _register_builtins(self) -> None:
        def word(name):
            def deco(fn):
                self.dictionary[name] = ("BUILTIN", fn)
                return fn

            return deco

        def binop(name, fn):
            def impl(vm):
                b = vm.pop()
                a = vm.pop()
                vm.push(fn(a, b))

            self.dictionary[name] = ("BUILTIN", impl)

        def cmp(name, fn):
            def impl(vm):
                b = vm.pop()
                a = vm.pop()
                vm.push(TRUE if fn(a, b) else FALSE)

            self.dictionary[name] = ("BUILTIN", impl)

        # Arithmetic — // and % are floor-based, matching Forth convention
        binop("+", lambda a, b: a + b)
        binop("-", lambda a, b: a - b)
        binop("*", lambda a, b: a * b)
        binop("/", lambda a, b: a // b)
        binop("MOD", lambda a, b: a % b)

        # Comparison — ANS Forth booleans: TRUE=-1, FALSE=0
        cmp("=", lambda a, b: a == b)
        cmp("<>", lambda a, b: a != b)
        cmp("<", lambda a, b: a < b)
        cmp(">", lambda a, b: a > b)
        cmp("<=", lambda a, b: a <= b)
        cmp(">=", lambda a, b: a >= b)

        # Bitwise/logical — Forth booleans are just integers, so these do double duty
        binop("AND", lambda a, b: a & b)
        binop("OR", lambda a, b: a | b)
        binop("XOR", lambda a, b: a ^ b)

        @word("INVERT")
        def _invert(vm):
            vm.push(~vm.pop())

        @word("NEGATE")
        def _negate(vm):
            vm.push(-vm.pop())

        # Stack manipulation
        @word("DUP")
        def _dup(vm):
            a = vm.pop()
            vm.push(a)
            vm.push(a)

        @word("DROP")
        def _drop(vm):
            vm.pop()

        @word("SWAP")
        def _swap(vm):
            b = vm.pop()
            a = vm.pop()
            vm.push(b)
            vm.push(a)

        @word("OVER")
        def _over(vm):
            b = vm.pop()
            a = vm.pop()
            vm.push(a)
            vm.push(b)
            vm.push(a)

        @word("ROT")
        def _rot(vm):
            c = vm.pop()
            b = vm.pop()
            a = vm.pop()
            vm.push(b)
            vm.push(c)
            vm.push(a)

        # Memory
        @word("@")
        def _fetch(vm):
            addr = vm.pop()
            vm.push(vm.memory[addr])

        @word("!")
        def _store(vm):
            addr = vm.pop()
            value = vm.pop()
            vm.memory[addr] = value

        # Loop index
        @word("I")
        def _loop_index(vm):
            if not vm.loop_stack:
                raise ForthError("I used outside a DO ... LOOP")
            vm.push(vm.loop_stack[-1])

        # Output
        @word(".")
        def _print(vm):
            vm._output.append(str(vm.pop()))

        @word("EMIT")
        def _emit(vm):
            vm._output.append(chr(vm.pop()))

        @word("CR")
        def _cr(vm):
            vm._output.append("\n")
