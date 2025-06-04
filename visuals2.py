import os
import json
import time
import requests
import logging
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("leonardo_downloader.log")  # Optional: Log to a file
    ]
)

# Load environment variables from .env file
load_dotenv()

# Configuration
API_KEY = os.getenv('LEONARDO_API_KEY')
if not API_KEY:
    logging.error("API key not found. Please set LEONARDO_API_KEY in your .env file.")
    exit(1)

AUTHORIZATION = f"Bearer {API_KEY}"

HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": AUTHORIZATION
}

LEONARDO_API_ENDPOINT = "https://cloud.leonardo.ai/api/rest/v1"
OUTPUT_DIR = "downloaded_content"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Only use Leonardo Anime XL model
ANIME_XL_MODEL = {
    "id": "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3",
    "name": "Leonardo Phoenix 1.0",
    "width": 576,
    "height": 1024,
    "num_images": 2,
    "alchemy": True,
    "enhancePrompt": False,
    "photoReal": False,
    "photoRealVersion": "",
    "presetStyle": "CINEMATIC"
}

def get_model_config_by_style(style=None):
    """
    Stubbed style selector: ignores input and always returns Anime XL config.
    """
    reason = "Overriding to use Leonardo Anime XL exclusively."
    return ANIME_XL_MODEL, reason

def generate_image(prompt, model_config=ANIME_XL_MODEL):
    if isinstance(model_config, tuple):
        model_config = model_config[0]
    url = f"{LEONARDO_API_ENDPOINT}/generations"
    payload = {
        "height": model_config['height'],
        "modelId": model_config['id'],
        "prompt": prompt,
        "width": model_config['width'],
        "num_images": model_config['num_images'],
        "alchemy": model_config['alchemy'],
        "photoReal": model_config['photoReal'],
        "photoRealVersion": model_config['photoRealVersion'],
        "enhancePrompt": model_config['enhancePrompt'],
        "presetStyle": model_config['presetStyle']
    }
    logging.info(f"Image generation request (Anime XL) at {model_config['width']}x{model_config['height']} for prompt: {prompt}")
    try:
        response = requests.post(url, json=payload, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        gen = data.get('generations_by_pk', {}) or data.get('sdGenerationJob', {})
        generation_id = gen.get('id') or gen.get('generationId')
        if generation_id:
            logging.info(f"Image generation initiated. Generation ID: {generation_id}")
            return generation_id
        logging.error(f"No generation ID found in response: {json.dumps(data, indent=4)}")
    except Exception as err:
        logging.error(f"Error during image generation: {err}")
    return None

def poll_generation_status(generation_id, wait_time=10, max_retries=30):
    url = f"{LEONARDO_API_ENDPOINT}/generations/{generation_id}"
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=HEADERS)
            response.raise_for_status()
            data = response.json()
            status = (data.get('status') or
                      data.get('generations_by_pk', {}).get('status') or
                      data.get('sdGenerationJob', {}).get('status'))
            status = status.lower() if status else None
            logging.info(f"Polling attempt {attempt}/{max_retries}. Status: {status}")
            if status == 'complete':
                logging.info("Generation complete.")
                return data
            if status == 'failed':
                logging.error("Generation failed.")
                return None
            time.sleep(wait_time)
        except Exception as err:
            logging.error(f"Polling error: {err}")
    logging.error("Exceeded maximum polling attempts. Generation incomplete.")
    return None

def extract_image_url(data):
    for key in ['generations_by_pk', 'sdGenerationJob']:
        images = data.get(key, {}).get('generated_images', [])
        if images:
            url = images[0].get('url') or images[0].get('imageUrl')
            if url:
                logging.info(f"Extracted Image URL: {url}")
                return url
    logging.error(f"No image URL found in data: {json.dumps(data, indent=4)}")
    return None

def download_content(url, filename):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        logging.info(f"Downloaded content to {filename}")
    except Exception as err:
        logging.error(f"Download error: {err}")

def process_visuals(script_path, output_script_path=None):
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        sections = data.get('sections', [])
        for idx, section in enumerate(sections, 1):
            prompt = section.get('visual', {}).get('prompt')
            if prompt:
                gen_id = generate_image(prompt)
                time.sleep(1.5)
                if not gen_id:
                    continue
                result = poll_generation_status(gen_id)
                if not result:
                    continue
                img_url = extract_image_url(result)
                if not img_url:
                    continue
                ext = os.path.splitext(urlparse(img_url).path)[1] or '.jpg'
                out_path = os.path.join(OUTPUT_DIR, f'section_{idx}_image{ext}')
                download_content(img_url, out_path)
                section['visual']['image_path'] = out_path
            for seg_i, seg in enumerate(section.get('segments', []), 1):
                prompt = seg.get('visual', {}).get('prompt')
                if prompt:
                    gen_id = generate_image(prompt)
                    time.sleep(1.5)
                    result = poll_generation_status(gen_id)
                    if not result:
                        continue
                    img_url = extract_image_url(result)
                    ext = os.path.splitext(urlparse(img_url).path)[1] or '.jpg'
                    out_path = os.path.join(OUTPUT_DIR, f'section_{idx}_segment_{seg_i}_image{ext}')
                    download_content(img_url, out_path)
                    seg['visual']['image_path'] = out_path
        if output_script_path:
            with open(output_script_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        return data
    except Exception as e:
        logging.error(f"Error processing visuals: {e}")
        return None

def main():
    input_json = 'video_script.json'
    output_json = 'video_script_with_anime_xl.json'
    process_visuals(input_json, output_json)

if __name__ == '__main__':
    main()
