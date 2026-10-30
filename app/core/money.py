"""Money helpers. All amounts are integer rupees."""
import math
from fractions import Fraction


def floor_to(x: Fraction | int | float, step: int) -> int:
    """Round down to a multiple of `step` (floor50 in the spec)."""
    return math.floor(Fraction(x) / step) * step


def round_half_up(x: Fraction | int | float) -> int:
    """Python's round() rounds halves to even (round(2.5) == 2). Money rounds halves up."""
    return math.floor(Fraction(x) + Fraction(1, 2))


def inr(amount: int) -> str:
    """Indian digit grouping: 1800 → ₹1,800; 150000 → ₹1,50,000."""
    sign = "-" if amount < 0 else ""
    s = str(abs(int(amount)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{sign}₹{s}"
