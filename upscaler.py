#!/usr/bin/env python3
import os
import json
import argparse
from pathlib import Path

def upscale_image(image_path: Path) -> Path:
    upscaled_path = image_path.parent / f"upscaled_{image_path.name}"
    curl_cmd = f'curl -s -X POST "http://192.168.1.154:5700/upscale?model=x4" -F "file=@{image_path}" --output {upscaled_path}'
    os.system(curl_cmd)

    if upscaled_path.exists() and upscaled_path.stat().st_size > 0:
        return upscaled_path
    else:
        print(f"[WARNING] Upscaling failed or produced empty file for: {image_path}")
        return image_path  # fallback to original

def process_json(json_path: Path):
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    changed = False

    for section in data.get("sections", []):
        for segment in section.get("segments", []):
            visual = segment.get("visual", {})
            if "image_path" in visual:
                original_path = Path(visual["image_path"])
                if not original_path.exists():
                    print(f"[SKIP] Missing file: {original_path}")
                    continue

                upscaled_path = upscale_image(original_path)
                if upscaled_path != original_path:
                    visual["image_path"] = str(upscaled_path)
                    changed = True

    if changed:
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"[UPDATED] JSON saved with upscaled paths: {json_path}")
    else:
        print("[NO CHANGE] No visuals were upscaled or updated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upscale visuals in a video script JSON.")
    parser.add_argument("json_file", type=str, help="Path to the video script JSON file.")
    args = parser.parse_args()

    process_json(Path(args.json_file))
