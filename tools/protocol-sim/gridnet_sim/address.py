"""Hierarchical 4-byte GRIDNET addressing (docs/protocol.md)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Address:
    city: int
    district: int
    building: int
    unit: int

    def __post_init__(self) -> None:
        for name in ("city", "district", "building", "unit"):
            value = getattr(self, name)
            if not 0 <= value <= 0xFF:
                raise ValueError(f"Address.{name}={value} out of range 0..255")

    def to_bytes(self) -> bytes:
        return bytes((self.city, self.district, self.building, self.unit))

    @classmethod
    def from_bytes(cls, data: bytes) -> "Address":
        if len(data) != 4:
            raise ValueError(f"address must be 4 bytes, got {len(data)}")
        return cls(*data)

    @classmethod
    def parse(cls, text: str) -> "Address":
        parts = text.strip().split(".")
        if len(parts) != 4:
            raise ValueError(f"address must have 4 dotted parts: {text!r}")
        return cls(*(int(p) for p in parts))

    def __str__(self) -> str:
        return f"{self.city:02d}.{self.district:02d}.{self.building:02d}.{self.unit:02d}"

    def __repr__(self) -> str:
        return f"Address({self})"


# Broadcast address: FF.FF.FF.FF
BROADCAST = Address(0xFF, 0xFF, 0xFF, 0xFF)
