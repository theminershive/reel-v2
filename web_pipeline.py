import json
from pathlib import Path
from datetime import datetime

from narration_and_style import generate_video_script
from topic import generate_topic
from workflow_utils import generate_and_download_images
from tts import process_tts
from video_assembler import assemble_video
from config import VIDEO_SCRIPTS_DIR


def sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in (" ", "_") else "_" for c in name).strip().replace(" ", "_")


def run_pipeline(
    topic: str,
    length: int,
    voice: str,
    style: str,
    num_sections: int = 3,
    num_segments: int = 3,
    prompt_template: str | None = None,
    topic_prompt: str | None = None,
) -> str:
    if not topic and topic_prompt:
        suggestion = generate_topic(topic_prompt)
        if suggestion:
            topic = suggestion["title"]
            length = suggestion.get("length", length)
            num_sections = suggestion.get("sections", num_sections)
            num_segments = suggestion.get("segments_per_section", num_segments)
        else:
            raise ValueError("Failed to generate topic from prompt")

    script = generate_video_script(
        topic,
        length,
        "1080x1920",
        num_sections,
        num_segments,
        voice=voice,
        style=style,
        prompt_template=prompt_template,
    )
    script = generate_and_download_images(script)
    script = process_tts(script)

    fname = sanitize(topic) + "_" + datetime.now().strftime("%Y%m%d%H%M%S") + ".json"
    script_path = VIDEO_SCRIPTS_DIR / fname
    with open(script_path, "w") as f:
        json.dump(script, f, indent=2)

    assemble_video(str(script_path))

    with open(script_path) as f:
        data = json.load(f)
    return data.get("final_video")
