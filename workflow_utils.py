"""Shared helpers for the video workflow."""
from __future__ import annotations

import os
from pathlib import Path
import requests

import captions
from visuals import (
    get_model_config_by_style,
    generate_image,
    poll_generation_status,
    extract_image_url,
    download_content,
)
from config import VISUALS_DIR


def generate_and_download_images(script: dict) -> dict:
    """Generate visuals for each segment and save the upscaled images."""
    model_config = get_model_config_by_style(
        script["settings"].get("image_generation_style")
    )
    for section in script.get("sections", []):
        for segment in section.get("segments", []):
            prompt = segment["visual"]["prompt"]
            generation_id = generate_image(prompt, model_config)
            if not generation_id:
                raise RuntimeError(
                    f"Failed to start image generation for prompt: {prompt}"
                )
            data = poll_generation_status(generation_id)
            if not data:
                raise RuntimeError("Image generation did not complete.")
            image_url = extract_image_url(data)
            if not image_url:
                raise RuntimeError("Could not extract image URL.")
            img_filename = (
                f"section_{section['section_number']}_segment_{segment['segment_number']}.png"
            )
            img_path = VISUALS_DIR / img_filename
            download_content(image_url, str(img_path))

            upscaled_path = img_path.parent / f"upscaled_{img_path.name}"
            with open(img_path, "rb") as f:
                resp = requests.post(
                    "http://192.168.1.154:5700/upscale?model=x4",
                    files={"file": f},
                    timeout=600,
                )
                resp.raise_for_status()
                upscaled_path.write_bytes(resp.content)
            segment["visual"]["image_path"] = str(upscaled_path)
    return script


def create_captions(video_path: str) -> list[dict]:
    """Generate Whisper captions for a video."""
    audio_temp = captions.extract_audio(video_path)
    transcription = captions.transcribe_audio_whisper(audio_temp)
    cap_list = captions.generate_captions_from_whisper(transcription)
    try:
        if audio_temp and Path(audio_temp).exists():
            Path(audio_temp).unlink()
    except Exception:
        pass
    return cap_list
