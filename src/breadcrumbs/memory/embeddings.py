from __future__ import annotations

from hashlib import sha256
import math


def hash_embedding(text: str, dims: int = 64) -> list[float]:
    """Create a deterministic local demo embedding without sending text anywhere."""

    if dims <= 0:
        raise ValueError("dims must be positive")

    values: list[float] = []
    seed = text.encode("utf-8", errors="ignore")
    counter = 0
    while len(values) < dims:
        digest = sha256(seed + counter.to_bytes(4, "big")).digest()
        for byte in digest:
            values.append((byte / 127.5) - 1.0)
            if len(values) == dims:
                break
        counter += 1

    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [round(value / norm, 6) for value in values]
