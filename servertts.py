# app.py
from typing import Optional
import io

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from TTS.api import TTS
import soundfile as sf

app = FastAPI(title="Coqui-TTS Server")

# — Initialize your multi-speaker model once —
tts = TTS(model_name="tts_models/en/vctk/vits")  # this is multi-speaker :contentReference[oaicite:0]{index=0}

class TTSRequest(BaseModel):
    text: str
    speaker: Optional[str] = None  # must match one of tts.speakers
    language: Optional[str] = None

@app.get("/voices", summary="List available speakers & languages")
async def list_voices():
    data = {}
    if tts.is_multi_speaker:
        data["speakers"] = tts.speakers   # list of strings :contentReference[oaicite:1]{index=1}
    if tts.is_multi_lingual:
        data["languages"] = tts.languages
    return data

@app.post("/synthesize", summary="Synthesize text → WAV")
async def synthesize(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(400, "Text must not be empty")

    # Enforce speaker selection for multi-speaker models
    if tts.is_multi_speaker and not req.speaker:
        raise HTTPException(
            400,
            f"Model is multi-speaker; you must supply `speaker`. "
            f"Available: {tts.speakers}"
        )

    # Enforce language selection for multi-lingual models
    if tts.is_multi_lingual and not req.language:
        raise HTTPException(
            400,
            f"Model is multi-lingual; you must supply `language`. "
            f"Available: {tts.languages}"
        )

    # Perform TTS
    wav = tts.tts(
        text=req.text,
        speaker=req.speaker,
        language=req.language
    )

    # Stream back a WAV
    buf = io.BytesIO()
    sf.write(buf, wav, tts.synthesizer.output_sample_rate, format="WAV")
    buf.seek(0)
    return StreamingResponse(buf, media_type="audio/wav")
