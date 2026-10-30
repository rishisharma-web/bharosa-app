"""Helpers shared by the agents."""
import re


def rupee_figures(text: str) -> set[int]:
    """Every ₹/Rs amount in a text, as integers (₹2,000 / Rs. 2000 / 2000 rupees)."""
    out = set()
    for pat in (r"(?:₹|rs\.?\s*|inr\s*)\s*([\d,]+)", r"([\d,]+)\s*(?:rupaye|rupees|rupay|रुपये|ರೂಪಾಯಿ)"):
        for m in re.finditer(pat, text or "", re.I):
            digits = m.group(1).replace(",", "")
            if digits.isdigit():
                out.add(int(digits))
    return out
