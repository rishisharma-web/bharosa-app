"""Growth Agent (v2 spec §9.7), formerly Munim.

1. Plan wording: rewords the three code-computed actions. The same action ids must come back,
   once each, and every rupee figure must be one of that action's facts; ranking is never taken
   from the AI. Otherwise the templates stay.
2. Ask Munim (AI on only): a JSON tool loop over read-only tools (max 3 calls). Every rupee figure
   in the answer must appear in a tool result, or a template summary is returned instead.
"""
import json
from typing import Callable

from app.agents.common import rupee_figures
from app.ai import sarvam

WORD_SYSTEM = ("You word a kirana shop's weekly growth plan for the shopkeeper. You get three actions with "
               "facts. Return JSON {\"summary\": \"<= 35 words\", \"actions\": [{\"action_id\": \"...\", "
               "\"title\": \"<= 8 words\", \"why\": \"<= 30 words\"}]}. Keep the same action_ids. Use only "
               "rupee figures that appear in that action's facts. JSON only.")

ASK_SYSTEM = ("You are Munim, a copilot for a kirana shopkeeper. Answer using only facts from tools. "
              "Each turn reply with JSON: either {\"tool\": \"<name>\"} or {\"final\": \"<answer, <= 80 words>\"}. "
              "Tools: get_summary (shop totals), get_growth_plan, get_stock, list_overdue (overdue customers only), "
              "list_customers (every customer of this shop: amount owed, days overdue, safe limit, score band). "
              "For a question about a named customer, call list_customers. Amounts are in rupees; write them as ₹. "
              "Never invent numbers.")
MAX_TOOLS = 3


def _numbers(obj, out: set[int]) -> set[int]:
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(int(round(obj)))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers(v, out)
    return out


def summary_template(actions: list[dict]) -> str:
    return "Three things to do this week, in order of impact."


async def word_plan(actions: list[dict]) -> dict | None:
    """{"summary", "wording": {action_id: {"title", "why"}}} or None (keep templates)."""
    if not sarvam.enabled():
        return None
    out = await sarvam.chat_json(WORD_SYSTEM, json.dumps(
        [{"action_id": a["action_id"], "facts": a["facts"], "impact": a["impact"]} for a in actions], ensure_ascii=False))
    if not isinstance(out, dict) or not isinstance(out.get("actions"), list):
        return None
    by_id = {a["action_id"]: a for a in actions}
    got = {}
    for w in out["actions"]:
        aid = w.get("action_id") if isinstance(w, dict) else None
        if aid not in by_id or aid in got:
            return None
        title, why = str(w.get("title", "")), str(w.get("why", ""))
        allowed = _numbers({**by_id[aid]["facts"], "impact": by_id[aid]["impact"]}, set())
        if not title or not why or len(title.split()) > 10 or len(why.split()) > 40:
            return None
        if (rupee_figures(title) | rupee_figures(why)) - allowed:
            return None
        got[aid] = {"title": title, "why": why}
    if set(got) != set(by_id):
        return None
    summary = str(out.get("summary") or "")
    if rupee_figures(summary) - _numbers([a["facts"] for a in actions] + [a["impact"] for a in actions], set()):
        summary = summary_template(actions)
    return {"summary": summary[:300] or summary_template(actions), "wording": got}


async def ask(question: str, tools: dict[str, Callable[[], dict]]) -> dict:
    """{"answer", "steps", "source"}. AI must be on; the caller handles the off case."""
    messages = json.dumps({"question": question})
    steps, results = [], {}
    for _ in range(MAX_TOOLS + 1):
        out = await sarvam.chat_json(ASK_SYSTEM, messages + "\nTOOL RESULTS: " + json.dumps(results, ensure_ascii=False))
        if not isinstance(out, dict):
            break
        if isinstance(out.get("final"), str):
            if not (rupee_figures(out["final"]) - _numbers(results, set())):
                return {"answer": out["final"], "steps": steps, "source": "ai"}
            break
        name = out.get("tool")
        if name not in tools or len(steps) >= MAX_TOOLS:
            break
        results[name] = tools[name]()
        steps.append(name)
    summary = tools["get_summary"]()
    return {"answer": (f"Udhaar outstanding {summary['outstanding_text']}, overdue {summary['overdue_text']}. "
                       "Your growth plan on Home lists this week's three actions."),
            "steps": steps or ["get_summary"], "source": "template"}
