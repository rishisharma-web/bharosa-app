"""Customer personas (spec 4.6). Used by the Overview comparison simulation's synthetic population;
the demo world itself is written out by hand in seed.py."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    name: str
    takes_per_month: tuple[int, int]
    amount: tuple[int, int]
    score: tuple[int, int]


PERSONAS: dict[str, Persona] = {
    "punctual": Persona("punctual", (2, 4), (150, 600), (700, 820)),
    "salary_day": Persona("salary_day", (3, 6), (200, 700), (600, 720)),
    "late_payer": Persona("late_payer", (2, 5), (200, 800), (520, 640)),
    "chronic_defaulter": Persona("chronic_defaulter", (3, 6), (300, 900), (350, 500)),
    "cash_only": Persona("cash_only", (2, 4), (150, 500), (560, 660)),
}

# A typical kirana's regulars, ≈ 25/30/25/10/10 % (spec 4.2).
MIX = {"punctual": 14, "salary_day": 16, "late_payer": 14, "chronic_defaulter": 5, "cash_only": 6}
