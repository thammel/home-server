"""Splitting a receipt by its lines (ADR 0010)."""

import math
from collections.abc import Iterable
from fractions import Fraction


def to_cents(amount: float) -> int:
    return round(amount * 100)


def allocate(lines: Iterable[tuple[float, Iterable[int]]]) -> dict[int, int]:
    """Cents per person: each line split equally within its group.

    Exact parts are summed first and rounded once per person by largest remainder,
    so the result adds up to the lines' total to the cent.
    """
    exact: dict[int, Fraction] = {}
    for line_total, user_ids in lines:
        people = set(user_ids)
        part = Fraction(to_cents(line_total), len(people))
        for user_id in people:
            exact[user_id] = exact.get(user_id, Fraction(0)) + part
    cents = {user_id: math.floor(value) for user_id, value in exact.items()}
    left = int(sum(exact.values()) - sum(cents.values()))
    by_remainder = sorted(exact, key=lambda u: (cents[u] - exact[u], u))
    for user_id in by_remainder[:left]:
        cents[user_id] += 1
    return cents


def items_match(items, shares) -> bool | None:
    """None without lines; False once the shares were edited away from what the lines give."""
    if not items:
        return None
    derived = allocate((i.line_total, i.user_ids) for i in items)
    consumed: dict[int, int] = {}
    for share in shares:
        if share.share > 0:
            consumed[share.user_id] = consumed.get(share.user_id, 0) + to_cents(
                share.share
            )
    return {u: c for u, c in derived.items() if c} == consumed
