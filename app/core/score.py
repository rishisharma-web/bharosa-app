"""Bharosa Score (spec 7.4). Display helpers now; score triggers arrive with repayments."""

MIN_SCORE, MAX_SCORE, START_SCORE = 300, 900, 600


def clamp(score: int) -> int:
    return max(MIN_SCORE, min(MAX_SCORE, score))


def band(score: int) -> str:
    if score >= 800:
        return "Excellent"
    if score >= 700:
        return "Strong"
    if score >= 550:
        return "Good"
    return "Building"


def rewards(score: int) -> list[str]:
    out = []
    if score >= 700:
        out.append("Higher limits at all Paytm stores")
    if score >= 750:
        out.append("Partner offer: 2% cashback on groceries")
    return out
