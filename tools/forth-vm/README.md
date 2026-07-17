# GRIDNET Core Forth VM

A minimal Forth interpreter — the language-semantics prototype for the
sandboxed application VM described in
[`docs/firmware-arch.md`](../../docs/firmware-arch.md) ("Forth VM" section)
and [`docs/protocol.md`](../../docs/protocol.md) (`APP_DATA` / Forth
Application Protocol). This is the **core language only**: stacks,
dictionary, arithmetic, control flow, variables. It does not yet implement
the GRIDNET-specific parts — the 80×25 screen buffer, `KEY?`/`SEND-MSG`,
or the security sandbox (address lock, rate limiting, filesystem isolation)
described in those docs. Those are a separate follow-up once the core
language is settled.

No dependencies beyond the Python 3 standard library.

## Running it

```bash
cd tools/forth-vm
python3 run_demo.py --list
python3 run_demo.py fizzbuzz
python3 run_demo.py --repl        # interactive
python3 -m unittest discover -s tests -v
```

Four examples in `run_demo.py`: `factorial`, `fizzbuzz`, `fibonacci` (all
recursive/iterative definitions exercising `DO`/`LOOP`, `IF`/`ELSE`, and
recursion), and `corner-shop` (the market-order-system idea from the top
level README, adapted to what this core VM currently supports — no real
screen/keyboard yet). 36 unit tests in `tests/test_vm.py` cover the
tokenizer, every word group, and the error paths.

## What it implements

| Group | Words |
|---|---|
| Arithmetic | `+ - * / MOD NEGATE` |
| Comparison | `= <> < > <= >=` (ANS Forth booleans: `TRUE` is `-1`, `FALSE` is `0`) |
| Bitwise/logical | `AND OR XOR INVERT` |
| Stack | `DUP DROP SWAP OVER ROT` |
| Control flow | `IF ELSE THEN` · `BEGIN UNTIL` · `BEGIN WHILE REPEAT` · `DO LOOP` + `I` |
| Definitions | `: name ... ;` · `VARIABLE name` · `n CONSTANT name` · `@` `!` |
| Output | `.` `EMIT` `CR` `." string"` |
| Comments | `( ... )` and `\ to end of line` |

Recursion works by a word calling its own name from inside its definition
(`: FACT DUP 1 <= IF DROP 1 ELSE DUP 1 - FACT * THEN ;` — see
`run_demo.py`'s `factorial` example); there's no separate `RECURSE` word
since it isn't needed (see "Design simplifications" below).

## Example

```forth
: FIZZBUZZ 20 1 DO
    I 15 MOD 0 = IF ." FizzBuzz"
    ELSE I 3 MOD 0 = IF ." Fizz"
    ELSE I 5 MOD 0 = IF ." Buzz"
    ELSE I . THEN THEN THEN CR
LOOP ;
FIZZBUZZ
```

## Design simplifications (prototype vs. eventual embedded VM)

These are deliberate scope choices for a language-semantics prototype, not
oversights — see `forth_vm/vm.py`'s module docstring for the full reasoning:

- **Nested-list compilation, not threaded code.** A `: ... ;` definition
  compiles to a tree of Python tuples (e.g. `IF` holds its own true/false
  branch lists) rather than a flat instruction stream with branch/jump
  offsets. Real Forth — and the eventual embedded port — uses the latter
  because it's far cheaper on ~2KB RAM. The nested form is easier to get
  right and test, which is what this prototype is actually for.
- **Late binding.** A word call resolves by dictionary lookup at
  *execution* time, not bound to a specific definition at *compile* time.
  Real Forth binds at compile time, so redefining a word later doesn't
  retroactively change already-compiled callers; here it does (see
  `test_redefinition_uses_latest_definition`). This is also exactly what
  makes plain-name recursion work without a dedicated `RECURSE` word — the
  word's own name already resolves to its (by-then-complete) definition the
  first time it's actually called.
- **No `RECURSE`, `>R`/`R>`/`R@`, or `DOES>`.** Not needed for the
  control-flow and definition forms above; can be added if a follow-up
  needs them.

## Repository layout

```
tools/forth-vm/
├── README.md              (this file)
├── run_demo.py             CLI entry point + examples + REPL
├── forth_vm/
│   ├── __init__.py
│   └── vm.py               tokenizer, compiler, VM, builtins
└── tests/
    └── test_vm.py
```
