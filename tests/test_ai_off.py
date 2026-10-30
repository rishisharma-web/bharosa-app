"""With SARVAM_ENABLED=false no outbound HTTP is made and every flow in §5 completes (spec §14)."""
import httpx
import pytest
from conftest import counter, ok


@pytest.fixture
def no_network(monkeypatch):
    calls = []

    async def boom(self, *a, **k):
        calls.append(a)
        raise AssertionError("outbound HTTP while AI is off")

    monkeypatch.setattr(httpx.AsyncClient, "send", boom)
    return calls


def _front(w):
    return ok(w["soundbox"].get("/api/soundbox/state"))["front"]


def test_all_flows_with_ai_off(world, no_network):
    m, sb = world["merchant"], world["soundbox"]
    # A: known customers (free text goes through the rule parser, no AI)
    ok(sb.post("/api/soundbox/udhaar", json={"text": "Priya 340 udhaar"}))
    top = ok(sb.post("/api/soundbox/udhaar", json={"text": "Ramesh 340"}))
    assert top["text"] == "Caution. Give ₹200 on credit, collect ₹140 now."
    assert sb.post("/api/soundbox/udhaar", json={"text": "kuch bhi"}).status_code == 422
    ok(sb.post("/api/soundbox/accept", json={"override": False}))
    ok(world["C_RAMESH"].post(f"/api/requests/{_front(world)['token']}/confirm", json={"pay_method": "upi", "device_id": "a"}))
    # B: Portable Trust
    counter(world, "C_ANITA", 2_000, accept=False)
    nxt = ok(world["C_ANITA"].post(f"/api/requests/{_front(world)['token']}/share", json={"decision": "share"}))["next_token"]
    ok(world["C_ANITA"].post(f"/api/requests/{nxt}/confirm", json={"pay_method": "credit_line", "device_id": "b"}))
    # C: Diwali + Stock Advance
    ok(m.post("/api/merchant/growth/A_DIWALI/approve"))
    ok(m.post("/api/merchant/advance/A1/accept"))
    # D: reminders, reply, auto-pay, split
    ok(m.post("/api/merchant/growth/A_REMIND/approve"))
    ok(world["C_RAMESH"].post("/api/customer/messages/reply", json={"store_id": "S1", "text": "Salary 1 tareekh ko aati hai, tab de dunga"}))
    ok(world["C_RAMESH"].post("/api/customer/mandates", json={"store_id": "S1", "cap": 3_000, "collection_day": 2}))
    pay = ok(world["C_RAMESH"].post("/api/customer/pay", json={"store_id": "S1", "amount": 500, "method": "upi"}))
    assert (pay["merchant_share"], pay["lender_share"]) == (400, 100)
    # E: basket
    ok(m.post("/api/merchant/growth/A_BASKET/approve"))
    b = ok(world["C_PRIYA"].get("/api/customer/home"))["action_needed"]["basket_id"]
    ok(world["C_PRIYA"].post(f"/api/customer/baskets/{b}/accept"))
    # F: dispute
    counter(world, "C_PRIYA", 340)
    ok(world["C_PRIYA"].post(f"/api/requests/{_front(world)['token']}/dispute", json={"reason": "Wrong amount"}))
    # AI-only features answer politely
    assert ok(m.post("/api/merchant/ask", json={"question": "How am I doing?"}))["enabled"] is False
    assert sb.post("/api/voice/transcribe").status_code in (404, 422)
    assert sb.get("/api/voice/speak?text=hi").status_code == 404
    assert no_network == []
    assert ok(m.get("/api/merchant/home"))["stock"]["advance"]["repaid"] == 100
