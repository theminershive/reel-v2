#!/usr/bin/env python3

import os
import json
import time
import logging
import argparse
from pathlib import Path
import openai
from dotenv import load_dotenv

from config import VISUALS_DIR
from visuals2 import (
    generate_image as leonardo_generate_image,
    poll_generation_status,
    extract_image_url,
)
from visuals import download_content  # For downloading images

# ------------------- CONFIG -------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError("OPENAI_API_KEY not found in environment or .env file.")

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
openai.api_key = OPENAI_API_KEY
openai.log = "debug"
logging.basicConfig(level=logging.INFO)

# ----------------------------------------------

def sanitize_filename(name):
    return "".join(c if c.isalnum() or c in (' ', '_') else '_' for c in name).strip().replace(' ', '_')

def clean_prompt(prompt):
    # Remove **, "Title:", "Image prompt:", and any code blocks/backticks
    prompt = prompt.replace('**', '')
    prompt = prompt.replace('Title:', '')
    prompt = prompt.replace('Image prompt:', '')
    prompt = prompt.replace('`', '')
    prompt = prompt.strip()
    return prompt

def generate_special_thumbnails(script):
    title = script.get("social_media", {}).get("title", script.get("topic", ""))
    if not title:
        logging.warning("No title found for thumbnail generation.")
        return script

    # Strict GPT prompt, no Markdown/meta-lines allowed
    gpt_prompt = f"""
You are a professional AI prompt engineer specializing in YouTube thumbnail generation for AI image models like Leonardo.ai and Midjourney.

Given the YouTube video title: "{title}", your task is to produce two outputs.

Important formatting instructions:
- Do NOT use Markdown or asterisks.
- Do NOT write "Title:" or "Image prompt:" lines.
- Simply include the short phrase naturally in the description: e.g. '...the words Forgotten Female Pharaoh in bold at the top left...'
- Do NOT use quotation marks around the phrase in the image.
- Do NOT use code blocks in your response.
- Respond strictly in valid, compact JSON.

----
1. YouTube Thumbnail Prompt (1376x768):
    - Generate a short, click-worthy title phrase (max 4–7 words) derived from the video title.
    - Write a single detailed cinematic image generation prompt that:
        - Clearly integrates the phrase as visible, bold text in the scene,
        - Describes the scene’s setting, mood, lighting, and composition with vivid cues,
        - Specifies text placement, size, and contrast (e.g., glow, shadow, color) for readability,
        - Avoids generic phrases like 'poster', 'design', or any technical instructions.

2. Social Media Version Prompt (square, 1080x1080):
    - Use the SAME title phrase as above, integrated as visible bold text in the image.
    - Write a single detailed cinematic image generation prompt (same requirements as above, but for a square image).

----
Respond strictly in JSON format:

{{
    "youtube_thumbnail_prompt": "<prompt for YouTube (title phrase as visible text)>",
    "social_media_image_prompt": "<prompt for social media (same phrase as visible text)>"
}}
"""

    response = openai.ChatCompletion.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a prompt engineering assistant specializing in visuals."},
            {"role": "user", "content": gpt_prompt}
        ],
        temperature=0.7
    )
    # Parse GPT response
    raw = response.choices[0].message.content.strip()
    # Remove code block formatting if present
    if raw.startswith('```json'):
        raw = raw[7:]
    if raw.endswith('```'):
        raw = raw[:-3]
    raw = raw.strip()
    prompts = json.loads(raw)

    # Clean both prompts
    prompts['youtube_thumbnail_prompt'] = clean_prompt(prompts['youtube_thumbnail_prompt'])
    prompts['social_media_image_prompt'] = clean_prompt(prompts['social_media_image_prompt'])

    # Generate YouTube thumbnail image (1376x768)
    yt_model_config = {
        "id": "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3",
        "name": "Leonardo Phoenix 1.0",
        "width": 1376,
        "height": 768,
        "num_images": 1,
        "alchemy": True,
        "enhancePrompt": False,
        "photoReal": False,
        "photoRealVersion": "",
        "presetStyle": "CINEMATIC"
    }
    yt_gen_id = leonardo_generate_image(prompts["youtube_thumbnail_prompt"], yt_model_config)
    yt_poll = poll_generation_status(yt_gen_id)
    yt_url = extract_image_url(yt_poll)
    yt_raw_path = VISUALS_DIR / f"yt_raw_{int(time.time()*1000)}.png"
    download_content(yt_url, str(yt_raw_path))

    # Generate Social Media thumbnail image (1080x1080)
    sm_model_config = {
        "id": "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3",
        "name": "Leonardo Phoenix 1.0",
        "width": 1080,
        "height": 1080,
        "num_images": 1,
        "alchemy": True,
        "enhancePrompt": False,
        "photoReal": False,
        "photoRealVersion": "",
        "presetStyle": "CINEMATIC"
    }
    sm_gen_id = leonardo_generate_image(prompts["social_media_image_prompt"], sm_model_config)
    sm_poll = poll_generation_status(sm_gen_id)
    sm_url = extract_image_url(sm_poll)
    sm_raw_path = VISUALS_DIR / f"social_raw_{int(time.time()*1000)}.png"
    download_content(sm_url, str(sm_raw_path))

    # Save AI-generated images as thumbnails
    script["thumbnails"] = {
        "youtube": str(yt_raw_path),
        "social": str(sm_raw_path)
    }
    return script

def main():
    parser = argparse.ArgumentParser(description="Generate thumbnails for a video script JSON.")
    parser.add_argument("--json", required=True, help="Input script JSON path.")
    parser.add_argument("--output", help="Output JSON path (defaults to input).")
    args = parser.parse_args()
    in_path = Path(args.json)
    out_path = Path(args.output) if args.output else in_path
    if not in_path.exists():
        logging.error(f"Missing JSON: {in_path}")
        return
    with open(in_path, encoding="utf-8") as f:
        data = json.load(f)
    updated = generate_special_thumbnails(data)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=4)
    print(json.dumps(updated.get("thumbnails", {}), indent=2))

if __name__ == "__main__":
    main()
