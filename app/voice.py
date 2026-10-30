"""One short spoken line per event on the Soundbox page (v2 spec §9.8). AI on only.

The line is translated into the store's voice language by the chat model; if translation fails,
or changes a rupee figure, nothing is spoken (the text is always on screen anyway)."""
from app import bus
from app.agents.common import rupee_figures
from app.ai import sarvam
from app.models import Store

TRANSLATE = ('Translate this shop announcement into {lang} for speaking aloud. Keep every number. '
             'Return JSON {{"text": "..."}}.')


async def spoken_line(t: bus.Tx, store_id: str, text: str, translate: bool = True) -> None:
    if not sarvam.enabled():
        return
    lang = t.s.get(Store, store_id).voice_lang
    line = text
    if translate and not lang.startswith("en"):
        out = await sarvam.chat_json(TRANSLATE.format(lang=lang), text)
        line = out.get("text") if isinstance(out, dict) else None
        if not isinstance(line, str) or not line or rupee_figures(line) - rupee_figures(text):
            return
    t.speak.append({"scope": f"soundbox:{store_id}", "text": line, "lang": lang})
