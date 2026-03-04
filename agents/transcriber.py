"""
agents/transcriber.py — Voice transcription agent.

Not a full ADK LlmAgent (no state, no output_key needed).
Just a clean async function that sends audio bytes to Gemini
and returns the transcript string.

Kept here (not in main.py) so all AI logic stays in agents/.
"""

import os
import base64
from dotenv import load_dotenv
from google import genai as google_genai

load_dotenv()


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/webm") -> dict:
    """
    Send raw audio bytes to Gemini 2.0 Flash for transcription.

    Args:
        audio_bytes: Raw audio data from MediaRecorder
        mime_type:   MIME type of the audio (audio/webm, audio/ogg, audio/wav)

    Returns:
        { "transcript": str, "error": str | None }
    """
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return {"transcript": "", "error": "GOOGLE_API_KEY not set in .env"}

    if not audio_bytes:
        return {"transcript": "", "error": "Empty audio received"}

    try:
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        client    = google_genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data":      audio_b64,
                        }
                    },
                    {
                        "text": (
                            "Transcribe the speech in this audio recording exactly as spoken. "
                            "Output ONLY the transcribed text — no quotes, no labels, no explanations."
                        )
                    },
                ]
            }],
        )

        transcript = (response.text or "").strip()
        print(f"[TRANSCRIBE] {len(audio_bytes):,} bytes → '{transcript[:120]}'")
        return {"transcript": transcript, "error": None}

    except Exception as e:
        print(f"[TRANSCRIBE ERROR] {e}")
        return {"transcript": "", "error": str(e)}