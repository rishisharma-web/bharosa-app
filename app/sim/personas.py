"""Customer personas (spec 4.6) and the fixed name pool used by the seed generator.

Names are a curated list rather than Faker so the seeded world does not change when a
library updates its locale data. Names that collide with demo characters (or the
"Kamala Kumar" unclear-payment payer) are deliberately absent, so the Counter and
Reconciliation agents never face an accidental lookalike.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    name: str
    takes_per_month: tuple[int, int]
    amount: tuple[int, int]
    score: tuple[int, int]
    verify_rate: float


PERSONAS: dict[str, Persona] = {
    "punctual": Persona("punctual", (2, 4), (150, 600), (700, 820), 0.9),
    "salary_day": Persona("salary_day", (3, 6), (200, 700), (600, 720), 0.9),
    "late_payer": Persona("late_payer", (2, 5), (200, 800), (520, 640), 0.85),
    "chronic_defaulter": Persona("chronic_defaulter", (3, 6), (300, 900), (350, 500), 0.8),
    "cash_only": Persona("cash_only", (2, 4), (150, 500), (560, 660), 0.6),
}

# 55 generated customers at S1 ≈ 25/30/25/10/10 %
S1_MIX = {"punctual": 14, "salary_day": 16, "late_payer": 14, "chronic_defaulter": 5, "cash_only": 6}
S2_MIX = {"punctual": 13, "salary_day": 15, "late_payer": 12, "chronic_defaulter": 5, "cash_only": 5}

FIRST_NAMES = [
    "Arjun", "Deepa", "Mahesh", "Lalitha", "Ganesh", "Savitha", "Prakash", "Kavya", "Naveen", "Shilpa",
    "Raghu", "Meena", "Sanjay", "Pooja", "Venkatesh", "Divya", "Harish", "Rekha", "Manjunath", "Sunita",
    "Kiran", "Asha", "Srinivas", "Bhavana", "Rajesh", "Geetha", "Mohan", "Nandini", "Anil", "Shobha",
    "Girish", "Usha", "Satish", "Padma", "Ravi", "Jyothi", "Naresh", "Sudha", "Dinesh", "Latha",
    "Vinod", "Radha", "Ashok", "Veena", "Shankar", "Hema", "Gopal", "Sarita", "Imran", "Farida",
    "Joseph", "Mary", "Abdul", "Nasreen", "Basavaraj", "Chaitra", "Yogesh", "Rashmi", "Tejas", "Sneha",
    "Pradeep", "Archana", "Lokesh", "Vani", "Siddharth", "Anjali", "Murali", "Pushpa", "Arun", "Smitha",
]

SURNAMES = [
    "Reddy", "Shetty", "Patil", "Iyer", "Menon", "Naik", "Hegde", "Joshi", "Bhandari", "Saxena",
    "Kulkarni", "Pillai", "Bhat", "Das", "Khan", "Fernandes", "Verma", "Singh", "Gupta", "Kini",
    "Murthy", "Prasad", "Acharya", "Kamath", "Shenoy", "Yadav", "Mishra", "Chandra", "Swamy", "Pai",
]

# Demo characters, the unclear-payment payer, the store owner and the distributor.
RESERVED_TOKENS = {
    "ramesh", "priya", "vikram", "suresh", "anita", "kamala", "kumar", "nair", "desai", "rao", "gowda",
    "lakshmi", "sharma", "sai",
}
