"""Side effects a handler asks the broadcaster to send after the transaction commits."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Effect:
    type: str  # audio | notify | caption | toast
    data: dict[str, Any] = field(default_factory=dict)

    def message(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data}


def audio(target: str, text: str, lang: str, url: str | None = None, kind: str = "alert") -> Effect:
    return Effect("audio", {"target": target, "url": url, "text": text, "lang": lang, "kind": kind})


def notify(target: str, title: str, body: str, action: dict | None = None) -> Effect:
    return Effect("notify", {"target": target, "title": title, "body": body, "action": action})


def caption(text: str) -> Effect:
    return Effect("caption", {"text": text})


def toast(text: str, level: str = "info") -> Effect:
    return Effect("toast", {"text": text, "level": level})
