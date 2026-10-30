"""First-call check for Sarvam (v2 spec §9.4). Usage: set SARVAM_ENABLED=true and SARVAM_API_KEY in .env,
then `python scripts/sarvam_smoke.py`. Prints results, never the key."""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.ai import sarvam  # noqa: E402


async def main() -> None:
    if not sarvam.enabled():
        print("SARVAM_ENABLED is false (or SARVAM_API_KEY is empty). Set both in .env to run this check.")
        return
    print("Chat:", await sarvam.chat_json("Reply only with JSON.", 'Return {"greeting": "<one word hello in Kannada>"}'))
    audio = await sarvam.text_to_speech("ರಮೇಶ್ ಇನ್ನೂರು ರೂಪಾಯಿ ಸಾಲವನ್ನು ದೃಢಪಡಿಸಿದರು", "kn-IN")
    if audio:
        with open("sarvam_tts_test.wav", "wb") as f:
            f.write(audio)
        print("TTS: wrote sarvam_tts_test.wav", len(audio), "bytes")
    else:
        print("TTS: failed")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
