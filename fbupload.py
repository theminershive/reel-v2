#!/usr/bin/env python3

import sys
import os
import json
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

USER_ACCESS_TOKEN = os.getenv('USER_ACCESS_TOKEN')
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID')
GRAPH_API_BASE = 'https://graph.facebook.com'

def get_page_access_token():
    if not USER_ACCESS_TOKEN:
        logging.error("USER_ACCESS_TOKEN not set.")
        sys.exit(1)
    url = f"{GRAPH_API_BASE}/v21.0/me/accounts"
    resp = requests.get(url, params={'access_token': USER_ACCESS_TOKEN})
    if resp.status_code != 200:
        logging.error(f"Failed to fetch pages: {resp.text}")
        sys.exit(1)
    for page in resp.json().get('data', []):
        if str(page.get('id')) == FACEBOOK_PAGE_ID:
            token = page.get('access_token')
            logging.info("Using Page access token.")
            return token
    logging.error("Page ID not found in /me/accounts.")
    sys.exit(1)

def upload(json_path):
    if not FACEBOOK_PAGE_ID:
        logging.error("FACEBOOK_PAGE_ID not set.")
        sys.exit(1)
    if not os.path.exists(json_path):
        logging.error(f"JSON file not found: {json_path}")
        sys.exit(1)

    page_token = get_page_access_token()

    with open(json_path) as f:
        metadata = json.load(f)

    social = metadata.get('social_media', {})
    title = social.get('title', '')
    description = social.get('description', '')

    # Check both social_media and top-level for youtube_url
    yt_url = social.get("youtube_url") or metadata.get("youtube_url")
    if yt_url:
        description = f"{description}\n\nWatch on YouTube: {yt_url}"

    image_file = metadata.get("thumbnails", {}).get("social")
    if not image_file or not os.path.exists(image_file):
        logging.error(f"Image file not found: {image_file}")
        sys.exit(1)

    logging.info(f"Uploading image instead of video: {image_file}")
    url = f"{GRAPH_API_BASE}/v21.0/{FACEBOOK_PAGE_ID}/photos"
    data = {
        'caption': description,
        'access_token': page_token
    }
    files = {'source': open(image_file, 'rb')}
    resp = requests.post(url, data=data, files=files)
    if resp.status_code != 200:
        logging.error(f"Upload failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    logging.info("Facebook image upload succeeded.")
    print(json.dumps(resp.json(), indent=2))

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python fbupload.py <path_to_json>")
        sys.exit(1)
    upload(sys.argv[1])
