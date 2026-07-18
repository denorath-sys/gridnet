# GRIDNET Forth VM

A Forth interpreter — the language-semantics and sandbox-model prototype
for the application VM described in
[`docs/firmware-arch.md`](../../docs/firmware-arch.md) ("Forth VM" section)
and [`docs/protocol.md`](../../docs/protocol.md) (`APP_DATA` / Forth
Application Protocol). Two layers:

- **`forth_vm/vm.py`** — the core language: stacks, dictionary, arithmetic,
  control flow, variables. No GRIDNET concepts at all.
- **`forth_vm/gridnet.py`** — `GridnetVM(ForthVM)`, adding the
  GRIDNET-specific words (`WRITE`, `KEY`/`KEY?`, `SEND-MSG`, `WAIT`) and
  enforcing the security sandbox rules from those two docs.

No dependencies beyond the Python 3 standard library.

## Running it

```bash
cd tools/forth-vm
python3 run_demo.py --list
python3 run_demo.py corner-shop-loop
python3 run_demo.py --repl        # interactive, core VM only
python3 -m unittest discover -s tests -v
```

Five examples in `run_demo.py`: `factorial`, `fizzbuzz`, `fibonacci` (core
VM — recursion, `DO`/`LOOP`, `IF`/`ELSE`), `corner-shop` (a single `ORDER`
call — draws the menu, sends nothing), and `corner-shop-loop` (the actual
`BEGIN ORDER 1000 WAIT AGAIN` main loop from the top-level README, now
genuinely running — see "GRIDNET words" below). 61 unit tests across
`tests/test_vm.py` (core) and `tests/test_gridnet.py` (GRIDNET words) cover
the tokenizer, every word group, error paths, and the sandbox rules.

## What the core VM implements

| Group | Words |
|---|---|
| Arithmetic | `+ - * / MOD NEGATE` |
| Comparison | `= <> < > <= >=` (ANS Forth booleans: `TRUE` is `-1`, `FALSE` is `0`) |
| Bitwise/logical | `AND OR XOR INVERT` |
| Stack | `DUP DROP SWAP OVER ROT` |
| Control flow | `IF ELSE THEN` · `BEGIN UNTIL` · `BEGIN WHILE REPEAT` · `BEGIN AGAIN` · `DO LOOP` + `I` |
| Definitions | `: name ... ;` · `VARIABLE name` · `n CONSTANT name` · `@` `!` |
| Output | `.` `EMIT` `CR` `." string"` (prints immediately) · `S" string"` (pushes the string as a value) |
| Comments | `( ... )` and `\ to end of line` |

Recursion works by a word calling its own name from inside its definition
(`: FACT DUP 1 <= IF DROP 1 ELSE DUP 1 - FACT * THEN ;`); no separate
`RECURSE` word is needed (see "Design simplifications" below).

`BEGIN ... AGAIN` is unconditional — no flag popped, loops forever — which
is exactly right for a terminal app's main loop on real hardware, but means
a test/demo harness needs a way to stop one. That's what `step_limit` is
for: `ForthVM(step_limit=N)` raises `StepLimitExceeded` after N ops,
regardless of what kind of loop is running. `corner-shop-loop` demonstrates
catching it as the normal, expected way to end a bounded run of an
intentionally-infinite app.

## GRIDNET words (`forth_vm/gridnet.py`)

| Word | Stack effect | Notes |
|---|---|---|
| `WRITE` | `( x y str -- )` | writes `str` at column `x`, row `y`; silently clipped to the 80×25 screen |
| `PAGE` | `( -- )` | clears the screen |
| `KEY` | `( -- key )` | pops the next queued keystroke (its ordinal); errors if none queued |
| `KEY?` | `( -- flag )` | `TRUE` if a keystroke is queued, else `FALSE` — standard ANS semantics |
| `BROADCAST` | `( -- addr )` | pushes the broadcast address (`FF.FF.FF.FF`, per `docs/protocol.md`) |
| `WAIT` | `( ms -- )` | advances the VM's *virtual* clock (`vm.now`) — no real sleeping |
| `SEND-MSG` | `( payload dst -- )` | sandbox-checked send (see below); `payload` is a string or a raw int (e.g. a keycode) |

A host feeds keystrokes with `vm.feed_keys("12")` (simulating a user typing)
and reads what an app tried to send via `vm.outbox` (a list of
`SentMessage(src, dst, payload, timestamp)`) — there's no real network
underneath, this validates the VM/sandbox side only.

### Sandbox rules enforced (`docs/firmware-arch.md` / `docs/protocol.md`)

| Rule | Enforced by |
|---|---|
| Address lock — app cannot change source address | no builtin writes to `vm.address`; it's fixed at `GridnetVM(address=...)` construction |
| Rate limit — max 5 packets/second | `SandboxViolation` in `SEND-MSG`, tracked against the virtual clock |
| Max message size — 256 bytes | `SandboxViolation` in `SEND-MSG` |
| Broadcast requires explicit permission | `SandboxViolation` unless `GridnetVM(allow_broadcast=True)` |
| Screen limited to 80×25 | `Screen.write()` clips out-of-bounds writes rather than erroring |
| Filesystem isolation per app | **not implemented** — this prototype has no file words at all yet, so there's nothing to isolate; adding fake file access just to sandbox it would test a feature that doesn't exist |

`SandboxViolation` is a subclass of `ForthError`, so a host can tell "the
app tried to do something the sandbox forbids" apart from "the app has a
language bug" without changing how it catches errors generally.

## Example — the corner shop, actually running

The top-level README's ~15-line market order system, now real:

```forth
: HEADER
    0 0 S" +---------------+" WRITE
    0 1 S" |  CORNER SHOP  |" WRITE
    0 2 S" +---------------+" WRITE ;
: ORDER
    HEADER
    0 4 S" 1. Bread  2. Milk" WRITE
    KEY? IF KEY S" 01.03.07.99" SEND-MSG THEN ;
: MAIN BEGIN ORDER 1000 WAIT AGAIN ;
```

One deviation from the README's original one-liner (`KEY? SEND-MSG`): `KEY?`
is a boolean check, in real Forth and here, not "the key that was pressed"
— so the working version checks it, then reads the key, then sends. The
README's line was illustrative pseudocode; this is its faithful working
equivalent, run in `run_demo.py`'s `corner-shop-loop` example.

## Design simplifications (prototype vs. eventual embedded VM)

Deliberate scope choices, not oversights — see `forth_vm/vm.py`'s and
`forth_vm/gridnet.py`'s module docstrings for the full reasoning:

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
  makes plain-name recursion work without a dedicated `RECURSE` word.
- **No `RECURSE`, `>R`/`R>`/`R@`, `DOES>`, or `EXIT`.** Not needed for the
  control-flow/definition forms above or for the GRIDNET words; the lack of
  `EXIT` is exactly why `BEGIN ... AGAIN` needs `step_limit` to stop in a
  test/demo harness rather than a word inside the app doing it.
- **Virtual clock, not real time.** `WAIT` and the rate-limit window both
  run off `vm.now`, a float the host advances — not `time.sleep()`. Keeps
  sandbox tests exact and instant (no real waiting for a 1-second rate-limit
  window to pass).
- **`SEND-MSG` payload is a string or int, not raw bytes.** A string covers
  ordinary app messages (order text, etc); a bare int covers sending a raw
  value like a keycode directly without round-tripping it through text.
  Real firmware ships actual bytes; this is close enough to validate the
  sandbox rules (size, rate, broadcast permission) without needing a byte-
  buffer/encoding layer this prototype doesn't otherwise have a use for.

## Repository layout

```
tools/forth-vm/
├── README.md              (this file)
├── run_demo.py             CLI entry point + examples + REPL
├── forth_vm/
│   ├── __init__.py
│   ├── vm.py               core: tokenizer, compiler, VM, builtins
│   └── gridnet.py            GridnetVM: screen, keyboard, SEND-MSG sandbox
└── tests/
    ├── test_vm.py
    └── test_gridnet.py
```
