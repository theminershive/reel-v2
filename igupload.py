#!/usr/bin/env python3

import sys
import os
import json
import time
import logging
import requests
import threading
import re
import socket
from urllib.parse import quote
from dotenv import load_dotenv
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

# Optional ngrok import
try:
    from pyngrok import ngrok
    HAS_NGROK = True
except ImportError:
    HAS_NGROK = False

# Pillow for thumbnail compression
from PIL import Image

load_dotenv()
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

APP_ID               = os.getenv('APP_ID')
APP_SECRET           = os.getenv('APP_SECRET')
SHORT_LIVED_TOKEN    = os.getenv('SHORT_LIVED_TOKEN')
INSTAGRAM_ACCOUNT_ID = os.getenv('INSTAGRAM_ACCOUNT_ID')
BASE_HTTP_PORT       = int(os.getenv('HTTP_PORT', '8300'))

TOKEN_RETRIES = 5
RETRY_BACKOFF = [1, 2, 4, 8, 16]  # seconds
MAX_IMG_BYTES  = 8 * 1024 * 1024  # 8 MB

def get_access_token():
    url = "https://graph.facebook.com/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": APP_ID,
        "client_secret": APP_SECRET,
        "fb_exchange_token": SHORT_LIVED_TOKEN
    }
    for attempt in range(1, TOKEN_RETRIES + 1):
        logging.debug(f"Token attempt {attempt}: GET {url} params={params}")
        resp = requests.get(url, params=params)
        logging.debug(f"Token response: {resp.status_code} {resp.text}")
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            if token:
                return token
            logging.error("No access_token in response")
            sys.exit(1)
        err = resp.json().get("error", {})
        if err.get("is_transient") and attempt < TOKEN_RETRIES:
            time.sleep(RETRY_BACKOFF[attempt-1])
            continue
        logging.error(f"Error fetching token: {resp.text}")
        sys.exit(1)
    logging.error("Token fetch failed after retries")
    sys.exit(1)

def prepare_thumbnail(path):
    """Compress & resize thumbnail under Instagram’s 8 MB limit, and convert RGBA->RGB."""
    # If under size limit, no change
    if os.path.getsize(path) <= MAX_IMG_BYTES:
        return path

    img = Image.open(path)

    # Convert RGBA or palette to RGB with white background
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize width to 1080px if wider
    if img.width > 1080:
        h = int(img.height * 1080 / img.width)
        img = img.resize((1080, h), Image.LANCZOS)

    out = os.path.splitext(path)[0] + "_ig.jpg"
    quality = 85
    img.save(out, "JPEG", quality=quality)
    while os.path.getsize(out) > MAX_IMG_BYTES and quality > 30:
        quality -= 10
        img.save(out, "JPEG", quality=quality)

    logging.info(f"Compressed thumbnail → {out} ({os.path.getsize(out)/1024:.1f} KB)")
    return out

class RangeHTTPRequestHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        ctype = self.guess_type(path)
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(404, "File not found")
            return None
        fs = os.fstat(f.fileno()); size = fs.st_size
        start, end = 0, size - 1
        if "Range" in self.headers:
            m = re.match(r"bytes=(\d+)-(\d*)", self.headers["Range"])
            if m:
                start = int(m.group(1))
                if m.group(2): end = int(m.group(2))
            if start > end or start < 0 or end >= size:
                self.send_error(416, "Requested Range Not Satisfiable")
                return None
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            length = end - start + 1
        else:
            self.send_response(200); length = size

        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.range = (start, end)
        return f

    def copyfile(self, source, outputfile):
        start, end = getattr(self, 'range', (0, None))
        remaining = None if end is None else (end - start + 1)
        buf = 64 * 1024
        while True:
            chunk = source.read(buf if remaining is None else min(buf, remaining))
            if not chunk: break
            outputfile.write(chunk)
            if remaining is not None:
                remaining -= len(chunk)
                if remaining <= 0: break

def find_free_port(start):
    port = start
    while port < start + 100:
        with socket.socket() as s:
            try:
                s.bind(('', port)); return port
            except OSError:
                port += 1
    logging.error("No free HTTP ports."); sys.exit(1)

def host_via_ngrok(path):
    port = find_free_port(int(os.getenv('HTTP_PORT', '8100')))
    dirname, name = os.path.split(path)
    os.chdir(dirname)
    httpd = ThreadingHTTPServer(('', port), RangeHTTPRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(1)
    tunnel = ngrok.connect(port, "http")
    url = f"{tunnel.public_url}/{name}"
    logging.info(f"ngrok URL → {url}")
    return httpd, thread, url

def fallback_transfersh(path):
    name = os.path.basename(path)
    logging.info("Uploading thumbnail to transfer.sh …")
    with open(path, 'rb') as f:
        r = requests.put(f"https://transfer.sh/{name}", data=f)
    if r.status_code == 200:
        url = r.text.strip()
        logging.info(f"transfer.sh URL → {url}")
        return url
    logging.error(f"transfer.sh failed: {r.status_code} {r.text}")
    sys.exit(1)

def upload(json_path):
    if not all([APP_ID, APP_SECRET, SHORT_LIVED_TOKEN, INSTAGRAM_ACCOUNT_ID]):
        logging.error("Missing Instagram credentials."); sys.exit(1)
    if not os.path.exists(json_path):
        logging.error(f"JSON not found: {json_path}"); sys.exit(1)

    token = get_access_token()
    data = json.load(open(json_path, encoding='utf-8'))
    soc  = data.get("social_media", {})
    title, desc = soc.get("title", ""), soc.get("description", "")
    tags        = soc.get("tags", [])
    parts = [title, desc] + ([", ".join(tags[:30])] if tags else [])
    caption = "\n\n".join(p for p in parts if p)
    yt = soc.get("youtube_url")
    if yt: caption += f"\n\nWatch on YouTube: {yt}"
    if len(caption) > 2200: caption = caption[:2197] + "..."

    thumb = data.get("thumbnails", {}).get("social")
    if not thumb or not os.path.exists(thumb):
        logging.error(f"Thumbnail not found: {thumb}"); sys.exit(1)
    thumb = prepare_thumbnail(thumb)

    httpd = thread = None
    public_url = None
    if HAS_NGROK:
        try:
            httpd, thread, public_url = host_via_ngrok(thumb)
            if requests.get(public_url, timeout=5).status_code != 200:
                raise Exception("Verify failed")
        except Exception:
            if httpd: httpd.shutdown(); thread.join()
            public_url = None

    if not public_url:
        public_url = fallback_transfersh(thumb)

    logging.info(f"Using URL → {public_url}")

    create_url = f"https://graph.facebook.com/v17.0/{INSTAGRAM_ACCOUNT_ID}/media"
    r1 = requests.post(create_url, data={
        "image_url":    public_url,
        "caption":      caption,
        "access_token": token
    })
    if r1.status_code != 200:
        logging.error(f"Create failed: {r1.status_code} {r1.text}"); sys.exit(1)
    cid = r1.json().get("id")

    pub_url = f"https://graph.facebook.com/v17.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
    r2 = requests.post(pub_url, data={"creation_id": cid, "access_token": token})
    if r2.status_code == 200:
        logging.info("Upload succeeded."); print(r2.json())
    else:
        logging.error(f"Publish failed: {r2.status_code} {r2.text}"); sys.exit(1)

    if HAS_NGROK and httpd:
        httpd.shutdown(); thread.join()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python igupload.py <path_to_json>")
        sys.exit(1)
    upload(sys.argv[1])
