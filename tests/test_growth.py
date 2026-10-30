"""Growth plan (spec §4.7) and the wording validator (§9.7)."""
import asyncio

from conftest import ok

from app.agents import growth_agent


def test_three_actions_in_order(world):
    actions = ok(world["merchant"].get("/api/merchant/home"))["growth_plan"]["actions"]
    assert [(a["action_id"], a["impact"], a["rank"]) for a in actions] == [
        ("A_DIWALI", 27_400, 1), ("A_REMIND", 4_300, 2), ("A_BASKET", 1_850, 3)]
    assert actions[0]["why"] == ("Last year your Diwali-week sales were about 1.6× normal. A ₹18,000 order could "
                                 "bring about ₹27,400 in extra sales.")
    assert actions[1]["why"] == "₹4,300 is overdue: Ramesh (19 days) and Vikram (41 days)."


def test_approvals_dispatch(world):
    m = world["merchant"]
    ok(m.post("/api/merchant/growth/A_REMIND/approve"))
    assert len(ok(world["C_RAMESH"].get("/api/customer/messages"))[0]["messages"]) == 1
    assert len(ok(world["C_VIKRAM"].get("/api/customer/messages"))[0]["messages"]) == 1
    ok(m.post("/api/merchant/growth/A_BASKET/approve"))
    assert ok(world["C_PRIYA"].get("/api/customer/home"))["action_needed"]["kind"] == "basket"
    assert m.post("/api/merchant/growth/A_BASKET/approve").status_code == 409


def test_ai_wording_with_wrong_figure_falls_back(world, monkeypatch):
    actions = ok(world["merchant"].get("/api/merchant/home"))["growth_plan"]["actions"]

    async def fake_chat(system, user):
        return {"summary": "x", "actions": [
            {"action_id": "A_DIWALI", "title": "Stock up", "why": "Order ₹99,999 now"},
            {"action_id": "A_REMIND", "title": "Remind", "why": "₹4,300 overdue"},
            {"action_id": "A_BASKET", "title": "Basket", "why": "₹1,850 basket"}]}

    monkeypatch.setattr("app.ai.sarvam.enabled", lambda: True)
    monkeypatch.setattr("app.ai.sarvam.chat_json", fake_chat)
    assert asyncio.run(growth_agent.word_plan(actions)) is None  # invented ₹99,999 → keep templates

    async def good_chat(system, user):
        return {"summary": "Three steps", "actions": [
            {"action_id": a["action_id"], "title": "Do it", "why": f"Worth ₹{a['impact']:,}"} for a in actions]}

    monkeypatch.setattr("app.ai.sarvam.chat_json", good_chat)
    out = asyncio.run(growth_agent.word_plan(actions))
    assert set(out["wording"]) == {"A_DIWALI", "A_REMIND", "A_BASKET"}
