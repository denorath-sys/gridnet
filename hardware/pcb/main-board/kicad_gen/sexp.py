"""Minimal S-expression helpers for pulling named blocks out of real KiCad
library files and re-emitting balanced text. Not a full parser — just
balanced-paren extraction, which is all we need to copy exact upstream
symbol definitions into our project-local library without retyping them
(and risking transcription errors) by hand.
"""

from __future__ import annotations

import uuid as _uuid


def extract_balanced(text: str, start_idx: int) -> str:
    """Given the index of an opening '(', return the matching balanced
    substring including both parens."""
    depth = 0
    i = start_idx
    in_string = False
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return text[start_idx : i + 1]
        i += 1
    raise ValueError("unbalanced parens")


def find_symbol_block(text: str, symbol_name: str) -> str:
    """Find `(symbol "symbol_name" ...)` as a *top-level* symbol definition
    (not a `_0_1`/`_1_1` sub-unit) and return the full balanced block."""
    needle = f'(symbol "{symbol_name}"'
    idx = 0
    while True:
        idx = text.find(needle, idx)
        if idx == -1:
            raise ValueError(f"symbol {symbol_name!r} not found")
        # Confirm exact name match (not a prefix of a longer name)
        after = text[idx + len(needle) :]
        if after[0] == "\n" or after.lstrip().startswith(")") or True:
            return extract_balanced(text, idx)
        idx += 1


def new_uuid() -> str:
    return str(_uuid.uuid4())


def indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.splitlines())
