#!/usr/bin/env python3

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv
from PIL import Image

load_dotenv()
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

def load_credentials():
    creds = None
    if os.path.exists("token2.json"):
        creds = Credentials.from_authorized_user_file("token2.json", SCOPES)
    if creds and creds.expired and creds.refresh_token:
        logging.info("Refreshing expired access token...")
        creds.refresh(Request())
    if not creds or not creds.valid:
        logging.error("token2.json missing or invalid.")
        raise RuntimeError("Invalid YouTube credentials.")
    return creds

def upload(json_path):
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    with open(json_path, "r") as f:
        metadata = json.load(f)

    # Determine which video file to upload
    video_file = metadata.get("final_video")
    if not video_file or not os.path.exists(video_file):
        final_dir = Path("final")
        vids = list(final_dir.glob("*.*"))
        if not vids:
            raise FileNotFoundError("No video files found in final directory.")
        video_file = str(max(vids, key=lambda p: p.stat().st_mtime))

    social = metadata.get("social_media", {})
    title = social.get("title", "Default Title")
    description = social.get("description", "")
    tags = social.get("tags", [])

    # Build YouTube client
    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    # Schedule publish 10 minutes from now
    scheduled_time = datetime.now(timezone.utc) + timedelta(minutes=10)
    publish_at = scheduled_time.isoformat().replace("+00:00", "Z")

    # Prepare upload body
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags[:500],
            "categoryId": "22"
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "publishAt": publish_at
        }
    }

    media = MediaFileUpload(video_file, mimetype="video/*", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    # Upload with progress logging
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logging.info(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    if not video_id:
        logging.error("Failed to retrieve video ID after upload.")
        raise RuntimeError("YouTube upload succeeded but no video ID returned.")
    yt_url = f"https://youtu.be/{video_id}"
    logging.info(f"YouTube upload scheduled: {yt_url} (will go live at {publish_at})")

    # Upload thumbnail if present and compress if needed
    thumbnail_path = metadata.get("thumbnails", {}).get("youtube")
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            orig_path = thumbnail_path
            img = Image.open(orig_path).convert("RGB")
            temp_thumb = orig_path.replace(".png", "_resized.jpg").replace(".webp", "_resized.jpg")

            max_width = 1280
            max_height = 720
            img.thumbnail((max_width, max_height), Image.ANTIALIAS)

            for quality in [90, 85, 80, 75, 70, 65, 60, 55, 50]:
                img.save(temp_thumb, format="JPEG", quality=quality, optimize=True)
                if os.path.getsize(temp_thumb) <= 2 * 1024 * 1024:
                    break
            else:
                raise ValueError("Could not reduce thumbnail under 2MB")

            thumbnail_path = temp_thumb
            logging.info(f"Uploading thumbnail from {thumbnail_path}")
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path)
            ).execute()
            logging.info("Thumbnail uploaded successfully.")

        except Exception as e:
            logging.warning(f"Failed to upload thumbnail: {e}")
    else:
        logging.warning("No valid thumbnail path found in JSON. Skipping thumbnail upload.")

    # Update JSON metadata
    social['youtube_url'] = yt_url
    metadata['social_media'] = social
    metadata['youtube_url'] = yt_url

    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=4)
    logging.info(f"Updated JSON metadata with YouTube URL at {json_path}")

    return yt_url

if __name__ == "__main__":
    if len(sys.argv) > 1:
        json_path = sys.argv[1]
        if not os.path.isfile(json_path):
            logging.error(f"Provided JSON path does not exist: {json_path}")
            sys.exit(1)
    else:
        ready_dir = Path("ready")
        json_files = list(ready_dir.glob("*.json"))
        if not json_files:
            logging.error("No JSON files found in ready directory.")
            sys.exit(1)
        json_path = str(max(json_files, key=lambda p: p.stat().st_mtime))

    try:
        upload(json_path)
    except Exception as e:
        logging.error(e)
        sys.exit(1)
