import os
import json
import time
import sys
import importlib
from pathlib import Path
from PIL import Image

# Ensure PIL ANTIALIAS compatibility
try:
    Image.ANTIALIAS
except AttributeError:
    Image.ANTIALIAS = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS

import numpy as np
import requests
from moviepy.editor import (
    ImageClip, AudioFileClip, VideoFileClip,
    concatenate_videoclips, CompositeAudioClip
)
from moviepy.video.fx.all import fadeout
from moviepy.audio.fx.all import audio_loop, audio_fadeout, audio_fadein
from config import VIDEO_SIZE as CFG_VIDEO_SIZE, FPS, FINAL_VIDEO_DIR

# -------------------- Constants --------------------
DEFAULT_BG_MUSIC_PATH = "./fallbacks/default_bg_music.mp3"
DEFAULT_TRANSITION_SOUND_PATH = "./fallbacks/default_transition.mp3"

FADEOUT_DURATION = 1.0
FADEIN_DURATION = FADEOUT_DURATION * 0.5
NARRATION_INITIAL_DELAY = 0.25  # start narration .25s after visual begins
END_EXTENSION = 0.5             # extend visuals and bg music .5s after narration ends

# -------------------- Environment --------------------

BANNED_SONGS = [
    "Upbeat Piano and Trumpet for Joyful Moments",
    "Song Title B",
    "Suspenseful Crime Background",
    "Dramatic Atmosphere", 
    "Serene and Melancholic Atmosphere for Discovery"
]

def is_banned(sound_info):
    return sound_info.get('name', '') in BANNED_SONGS

API_KEY = os.getenv("FREESOUND_API_KEY")
if not API_KEY:
    raise ValueError("FREESOUND_API_KEY environment variable not set.")

BASE_URL = "https://freesound.org/apiv2"
OUTPUT_SOUNDS = Path("./sounds")
OUTPUT_SOUNDS.mkdir(exist_ok=True)
BACKGROUND_MUSIC_USER = "Nancy_Sinclair"

# -------------------- Sound Helpers --------------------
def search_sounds(query, filters=None, sort="rating_desc", num_results=50):
    filter_str = (filters + ' AND ' if filters else '') + 'license:"Creative Commons 0"'
    params = { 'query': query, 'filter': filter_str, 'sort': sort,
               'fields': 'id,name,previews,license,duration,username,tags',
               'token': API_KEY, 'page_size': num_results }
    try:
        resp = requests.get(f"{BASE_URL}/search/text/", params=params)
        resp.raise_for_status()
        time.sleep(0.2)
        return resp.json().get('results', [])
    except Exception as e:
        print(f"[ERROR] search_sounds: {e}")
        return []

def download_sound(sound_info, output_path):
    if sound_info.get('license') != 'http://creativecommons.org/publicdomain/zero/1.0/':
        return None
    if output_path.exists():
        return str(output_path)
    url = sound_info.get('previews', {}).get('preview-hq-mp3')
    if not url:
        return None
    try:
        r = requests.get(url, stream=True)
        r.raise_for_status()
        with open(output_path, 'wb') as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        return str(output_path)
    except Exception as e:
        print(f"[ERROR] download_sound: {e}")
        return None

def generate_silence(duration, output_path):
    import wave, struct
    framerate = 44100
    nframes = int(duration * framerate)
    with wave.open(output_path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        for _ in range(nframes):
            wf.writeframes(struct.pack('h', 0))
    return str(output_path)

def fetch_background_music(bg_setting, total_duration):
    print(f"Fetching background music for duration {total_duration}s")
    fallback_keywords = ["calm","cinematic","happy","uplifting","emotional"]
    if bg_setting:
        results = search_sounds(bg_setting,
            filters=f'username:"{BACKGROUND_MUSIC_USER}" AND category:"Music" AND tag:"{bg_setting}"')
        for s in results:
            if not is_banned(s):
                path = OUTPUT_SOUNDS / f"bg_{s['id']}.mp3"
                got = download_sound(s, path)
                if got:
                    print(f"[SELECTED BG] {s['name']} (exact match)")
                    return got, s['name']
    for kw in fallback_keywords:
        results = search_sounds(kw, filters=f'username:"{BACKGROUND_MUSIC_USER}" AND category:"Music"')
        for s in results:
            if not is_banned(s):
                path = OUTPUT_SOUNDS / f"bg_{s['id']}.mp3"
                got = download_sound(s, path)
                if got:
                    print(f"[SELECTED BG] {s['name']} (fallback: {kw})")
                    return got, s['name']
    if Path(DEFAULT_BG_MUSIC_PATH).exists():
        print("[FALLBACK] Using default background music.")
        return DEFAULT_BG_MUSIC_PATH, "Default Background"
    print("[FALLBACK] Generating silence for background.")
    silence_path = OUTPUT_SOUNDS / "default_silence_bg.wav"
    generate_silence(total_duration + END_EXTENSION, silence_path)
    return str(silence_path), "Silence"

def fetch_transition(effect_name):
    results = search_sounds(effect_name or 'transition', filters='tag:transition')
    for s in results:
        if not is_banned(s):
            path = OUTPUT_SOUNDS / f"tr_{s['id']}.mp3"
            got = download_sound(s, path)
            if got:
                print(f"[SELECTED TRANSITION] {s['name']}")
                return got
    if Path(DEFAULT_TRANSITION_SOUND_PATH).exists():
        print("[FALLBACK] Using default transition sound.")
        return DEFAULT_TRANSITION_SOUND_PATH
    print("[FALLBACK] Generating silence for transition.")
    silence_path = OUTPUT_SOUNDS / "default_silence_tr.wav"
    generate_silence(0.5, silence_path)
    return str(silence_path)

# -------------------- Video Helpers --------------------
def zoom_effect(clip, zoom_factor=1.1):
    dur = clip.duration
    def scaling(t):
        p = t/dur
        return 1 + (zoom_factor - 1)*p if p<1 else zoom_factor
    return clip.resize(lambda t: scaling(t))

def assemble_video(script_json_path):
    data = json.loads(Path(script_json_path).read_text())
    settings = data.get('settings', {})
    vs = settings.get('video_size', f"{CFG_VIDEO_SIZE[0]}x{CFG_VIDEO_SIZE[1]}")
    w,h = map(int, vs.split('x')) if 'x' in vs else CFG_VIDEO_SIZE
    VIDEO_SIZE = (w,h)
    globals()['VIDEO_SIZE'] = VIDEO_SIZE
    importlib.import_module('config').VIDEO_SIZE = VIDEO_SIZE

    use_trans = settings.get('use_transitions', False)
    use_bg    = settings.get('use_background_music', False)
    bg_tag    = data.get('background_music_type','')

    clips, narrs, trans_auds = [], [], []
    timeline = 0.0
    first = True

    for sec in data.get('sections', []):
        segs = sec.get('segments', [])
        for seg in segs:
            dur = seg['narration'].get('duration', 0)
            ap = seg['narration'].get('audio_path')
            if ap and os.path.exists(ap):
                audio_clip = AudioFileClip(ap)
                start = timeline + (NARRATION_INITIAL_DELAY if first else 0)
                narrs.append(audio_clip.set_start(start))
                first = False
                dur = audio_clip.duration
            img = seg.get('visual',{}).get('image_path')
            if img and os.path.exists(img):
                ic = ImageClip(img).resize(VIDEO_SIZE)
                ext_start = NARRATION_INITIAL_DELAY if len(clips) == 0 else 0
                ext_end = END_EXTENSION if seg is segs[-1] and sec is data['sections'][-1] else 0
                ic = ic.set_duration(dur + ext_start + ext_end)
                ic = zoom_effect(ic).fx(fadeout, 0.15).set_start(timeline)
                clips.append(ic)
            if use_trans:
                tr = fetch_transition(seg.get('sound',{}).get('transition_effect',''))
                if tr:
                    ta = AudioFileClip(tr)
                    ta = ta.subclip(0, min(0.5, ta.duration)).volumex(settings.get('transition_volume', 0.05))
                    trans_auds.append(ta.set_start(max(timeline + dur - 0.1, 0)).fx(audio_fadeout, 0.3))
            timeline += dur

    if not clips:
        print("[ERROR] No clips to assemble.")
        return

    video = concatenate_videoclips(clips, method='compose')

    audio_end = 0.0
    for ac in narrs + trans_auds:
        try:
            audio_end = max(audio_end, ac.end)
        except Exception:
            audio_end = max(audio_end, ac.start + ac.duration)

    total_dur = max(video.duration, audio_end + END_EXTENSION)

    raw_audio = CompositeAudioClip(narrs + trans_auds).set_duration(total_dur)
    raw_vid = video.set_duration(total_dur).set_audio(raw_audio)
    raw_path = Path(FINAL_VIDEO_DIR) / f"{Path(script_json_path).stem}_raw.mp4"
    raw_vid.write_videofile(str(raw_path), fps=FPS, codec='libx264', audio_codec='aac')

    bg_file, bg_name = fetch_background_music(bg_tag, total_dur)
    final_path = Path(FINAL_VIDEO_DIR) / f"{Path(script_json_path).stem}.mp4"

    if use_bg and bg_file:
        base = VideoFileClip(str(raw_path))
        na = base.audio
        nd = na.duration
        ba = AudioFileClip(bg_file)
        bd = nd + END_EXTENSION
        ba = ba.fx(audio_loop, duration=bd) if ba.duration < bd else ba.subclip(0, bd)
        ba = ba.volumex(settings.get('bg_music_volume', 0.09)).fx(audio_fadein, FADEIN_DURATION).fx(audio_fadeout, FADEOUT_DURATION)
        combined = CompositeAudioClip([na.set_start(0), ba.set_start(0)]).set_duration(bd)
        final = base.set_duration(bd).set_audio(combined)
        print(f"[VERBOSE] Writing final video with BG to: {final_path}")
        final.write_videofile(str(final_path), fps=FPS, codec='libx264', audio_codec='aac')
        ba.close()
        base.close()
        final.close()
    else:
        raw_path.rename(final_path)

    data['raw_video'] = str(raw_path)
    data['final_video'] = str(final_path)
    Path(script_json_path).write_text(json.dumps(data, indent=2))

    # clean up open clips
    for clip in narrs + trans_auds:
        try:
            clip.close()
        except Exception:
            pass
    video.close()
    raw_audio.close()
    raw_vid.close()

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python video_assembler.py <script.json>")
        sys.exit(1)
    assemble_video(sys.argv[1])
