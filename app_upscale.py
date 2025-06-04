#!/usr/bin/env python3
import os
import json
import logging
import argparse
from pathlib import Path

# Suppress PIL debug logs
logging.getLogger("PIL").setLevel(logging.WARNING)

from narration_and_style import generate_video_script
from visuals_and_social import enrich_script

from tts import process_tts
from video_assembler import assemble_video
import captions
from workflow_utils import generate_and_download_images, create_captions
from overlay import add_text_overlay
from config import VISUALS_DIR, VIDEO_SCRIPTS_DIR, FINAL_VIDEO_DIR

from oauth_get2 import refresh_token
from ytuploader import upload as yt_upload
from fbupload import upload as fb_upload
from igupload import upload as ig_upload
from testemail import send_email

logging.basicConfig(level=logging.INFO)

for directory in [VISUALS_DIR, VIDEO_SCRIPTS_DIR, FINAL_VIDEO_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

def get_user_input():
    topic = input("Enter video topic: ").strip()
    current_info = input("Any current info or viral trend to include? (press Enter to skip): ").strip()
    size = input("Enter video size (e.g., 1080x1920) [1080x1920]: ").strip() or "1080x1920"
    length = int(input("Enter total video length in seconds: "))
    num_sections = int(input("Enter number of sections: "))
    num_segments = int(input("Enter number of segments per section: "))
    return topic, current_info, size, length, num_sections, num_segments



def main():
    parser = argparse.ArgumentParser(description="Run video workflow interactively or with a plan JSON.")
    parser.add_argument("--plan", type=str, help="Path to video plan JSON to run in non-interactive mode.")
    args = parser.parse_args()

    if args.plan:
        plan_path = Path(args.plan)
        if not plan_path.exists():
            print(f"Plan file {plan_path} not found.")
            return
        with open(plan_path) as f:
            plan = json.load(f)
        topic = plan.get("title", "")
        current_info = ""
        size = plan.get("resolution", "1080x1920")
        length = plan.get("structure", {}).get("length")
        num_sections = plan.get("structure", {}).get("sections")
        num_segments = plan.get("structure", {}).get("segments_per_section")
    else:
        topic, current_info, size, length, num_sections, num_segments = get_user_input()

    # 1. Generate initial video script
    script = generate_video_script(
        topic + (f" – {current_info}" if current_info else ""),
        length, size, num_sections, num_segments
    )
    if not script:
        print("Error generating video script.")
        return

    # 2. Enrich with visuals & social metadata
    script = enrich_script(script)

    # 3. Generate & download images
    script = generate_and_download_images(script)

    # 4. Generate TTS audio
    script = process_tts(script)

    # 5. Save script JSON
    script_json_path = VIDEO_SCRIPTS_DIR / f"{topic.replace(' ', '_')}_script.json"
    with open(script_json_path, "w") as f:
        json.dump(script, f, indent=4)
    logging.info(f"Script saved to {script_json_path}")

    # 6. Assemble video
    assemble_video(str(script_json_path))
    with open(script_json_path) as f:
        data = json.load(f)
    final_video_path = Path(data["final_video"]).resolve()
    if not final_video_path.exists():
        print(f"assemble_video did not produce expected file at {final_video_path} – aborting.")
        return
    logging.info(f"Final video created at {final_video_path}")

    # 7. Caption overlay
    captioned = final_video_path.with_name(final_video_path.stem + "_cap.mp4")
    caps = create_captions(str(final_video_path))
    if caps:
        try:
            captions.add_captions_to_video(
                input_video_path=str(final_video_path),
                transcription=caps,
                output_video_path=str(captioned)
            )
        except Exception as e:
            logging.warning(f"Captioning failed: {e}")
    else:
        logging.warning("No captions generated.")

    if not Path(captioned).exists():
        captioned = final_video_path

    # 8. Text overlay
    final_output = FINAL_VIDEO_DIR / f"{topic.replace(' ', '_')}_final.mp4"
    add_text_overlay(
        input_video_path=str(captioned),
        output_video_path=str(final_output),
        start_text="Comment your vote for the next topic!",
        end_text="Thanks for watching! Like and Subscribe!",
        start_duration=5,
        end_duration=5,
        start_font_path="Bangers-Regular.ttf",
        end_font_path="Bangers-Regular.ttf",
        start_fontsize=75,
        end_fontsize=75,
        text_color="white",
        bg_color=(0, 0, 0),
        col_opacity=0.3,
        padding=5,
        fade_in=True,
        fade_out=True,
        fade_duration=1,
    )
    logging.info(f"Video processing complete! Final video at {final_output}")
    # Update script JSON with overlay final video path
    try:
        with open(script_json_path, 'r+') as f:
            json_data = json.load(f)
            json_data['final_video'] = str(final_output)
            f.seek(0)
            json.dump(json_data, f, indent=4)
            f.truncate()
        logging.info(f"Script JSON updated with overlay final video path at {script_json_path}")
    except Exception as e:
        logging.warning(f"Failed to update script JSON: {e}")

    # 9. Upload sequence with one summary email
    report = []

    try:
        refresh_token()
        report.append("OAuth refresh: SUCCESS")
    except Exception as e:
        report.append(f"OAuth refresh: FAIL - {e}")

    try:
        yt_upload(str(script_json_path))
        report.append("YouTube upload: SUCCESS")
    except Exception as e:
        report.append(f"YouTube upload: FAIL - {e}")

    try:
        fb_upload(str(script_json_path))
        report.append("Facebook upload: SUCCESS")
    except Exception as e:
        report.append(f"Facebook upload: FAIL - {e}")

    try:
        ig_upload(str(script_json_path))
        report.append("Instagram upload: SUCCESS")
    except Exception as e:
        report.append(f"Instagram upload: FAIL - {e}")

    subject = f"Upload Report for {final_output.name}"
    body = "\n".join(report)
    send_email(subject, body)
    logging.info("Upload report emailed.")


if __name__ == "__main__":
    main()
