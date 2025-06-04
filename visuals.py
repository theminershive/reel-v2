import os
import json
import time
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("visuals.log")
    ]
)

# Local Flux API configuration
LOCAL_FLUX_API = os.getenv("LOCAL_FLUX_API", "http://192.168.1.154:8100")
GENERATE_ENDPOINT = f"{LOCAL_FLUX_API}/generate"

# Output directory for downloaded images
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "downloaded_content"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Default generation parameters
DEFAULT_WIDTH = int(os.getenv("FLUX_WIDTH", 1200))
DEFAULT_HEIGHT = int(os.getenv("FLUX_HEIGHT", 688))
DEFAULT_STEPS = int(os.getenv("FLUX_STEPS", 50))
DEFAULT_SCALE = float(os.getenv("FLUX_SCALE", 4.5))


def get_model_config_by_style(style: str) -> dict:
    """
    Returns configuration dict for a given style. Stubbed to use local Flux API.
    """
    return {
        "endpoint": GENERATE_ENDPOINT,
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
        "num_inference_steps": DEFAULT_STEPS,
        "guidance_scale": DEFAULT_SCALE,
        "enhance": False
    }


def get_model_from_config(config: dict) -> str:
    """
    Returns the model endpoint from config.
    """
    return config["endpoint"]



def generate_image(prompt: str, config: dict) -> str:
    """
    Submits an image generation request to the local Flux API.
    Returns the path to the saved image.
    """
    model_endpoint = config["endpoint"]
    payload = {
        "prompt": prompt,
        "width": config["width"],
        "height": config["height"],
        "num_inference_steps": config["num_inference_steps"],
        "guidance_scale": config["guidance_scale"],
        "enhance": config.get("enhance", False)
    }
    logging.info(f"POST {model_endpoint} -> {payload}")
    resp = requests.post(model_endpoint, json=payload, timeout=1200)
    resp.raise_for_status()

    filename = f"gen_{int(time.time() * 1000)}.png"
    file_path = OUTPUT_DIR / filename
    file_path.write_bytes(resp.content)
    logging.info(f"Image saved to {file_path}")
    return str(file_path)



def poll_generation_status(job_id: str, timeout: int = 300) -> str:
    """
    Stub for polling generation status.
    Since generate_image writes the file synchronously, return the job_id immediately.
    """
    return job_id


def extract_image_url(generation_output) -> str:
    """
    Stub to extract image path/URL from generation output.
    Here generation_output is already the file path.
    """
    return generation_output


def download_content(source: str, dest_path: str) -> None:
    """
    Downloads or copies generated content to final destination.
    Supports HTTP URLs or local file paths.
    """
    if source.startswith("http://") or source.startswith("https://"):
        resp = requests.get(source, stream=True, timeout=120)
        resp.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(1024):
                f.write(chunk)
    else:
        # local file, copy
        Path(dest_path).write_bytes(Path(source).read_bytes())
    logging.info(f"Downloaded content to {dest_path}")


def process_visuals(script_path: str, output_script_path: str = None) -> dict:
    """
    Processes a JSON script: generates visuals for each prompt.
    Patches in image_path fields.
    """
    with open(script_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for s_idx, section in enumerate(data.get('sections', []), start=1):
        prompt = section.get('visual', {}).get('prompt')
        if prompt:
            cfg = get_model_config_by_style(section.get('style', 'default'))
            model = get_model_from_config(cfg)
            job_id = generate_image(prompt, cfg)
            ready = poll_generation_status(job_id)
            img_path = extract_image_url(ready)
            # Move to final visuals directory
            final_name = f"section_{s_idx}.png"
            final_path = OUTPUT_DIR / final_name
            download_content(img_path, str(final_path))
            section['visual']['image_path'] = str(final_path)

        for seg_idx, seg in enumerate(section.get('segments', []), start=1):
            sprompt = seg.get('visual', {}).get('prompt')
            if sprompt:
                cfg = get_model_config_by_style(seg.get('style', 'default'))
                model = get_model_from_config(cfg)
                job_id = generate_image(sprompt, cfg)
                ready = poll_generation_status(job_id)
                img_path = extract_image_url(ready)
                final_name = f"section_{s_idx}_segment_{seg_idx}.png"
                final_path = OUTPUT_DIR / final_name
                download_content(img_path, str(final_path))
                seg['visual']['image_path'] = str(final_path)

    if output_script_path:
        with open(output_script_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    return data


def main():
    import sys
    input_json = sys.argv[1] if len(sys.argv) > 1 else 'video_script.json'
    output_json = sys.argv[2] if len(sys.argv) > 2 else 'video_script_with_images.json'
    process_visuals(input_json, output_json)


if __name__ == '__main__':
    main()
