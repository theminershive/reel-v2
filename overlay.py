#!/usr/bin/env python3
import os
import sys
import json
import argparse
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip

def add_text_overlay(input_video_path, output_video_path,
                     start_text, end_text,
                     start_duration, end_duration,
                     start_font_path, end_font_path,
                     start_fontsize, end_fontsize,
                     text_color, bg_color, col_opacity, padding,
                     fade_in=False, fade_out=False, fade_duration=1,
                     position=None):
    """Adds start and end text overlays to a video."""
    try:
        video = VideoFileClip(input_video_path)
    except Exception as e:
        print(f"Error loading video: {e}")
        sys.exit(1)

    video_width, video_height = video.size
    pos = position if position is not None else ('center', int(video_height * 0.2))

    def create_text_clip(text, duration, start_time, font_path, fontsize, allow_fade_in=True, allow_fade_out=True):
        try:
            txt = TextClip(
                txt=text,
                fontsize=fontsize,
                font=font_path,
                color=text_color,
                method='caption',
                size=(video_width - 2*padding, None),
                align='center'
            )
        except Exception as e:
            print(f"Error creating TextClip with font '{font_path}': {e}")
            sys.exit(1)
        bg = txt.on_color(
            size=(txt.w + 2*padding, txt.h + 2*padding),
            color=bg_color,
            pos=('center', 'center'),
            col_opacity=col_opacity
        )
        clip = bg.set_start(start_time).set_duration(duration)
        if fade_in and allow_fade_in:
            clip = clip.crossfadein(fade_duration)
        if fade_out and allow_fade_out:
            clip = clip.crossfadeout(fade_duration)
        return clip.set_position(pos)

    start_clip = create_text_clip(start_text, start_duration, 0, start_font_path, start_fontsize, allow_fade_in=False, allow_fade_out=False)
    end_start = max(video.duration - end_duration, 0)
    end_clip = create_text_clip(end_text, end_duration, end_start, end_font_path, end_fontsize, allow_fade_in=True, allow_fade_out=True)

    out = CompositeVideoClip([video, start_clip, end_clip])
    try:
        out.write_videofile(output_video_path, codec='libx264', audio_codec='aac')
    except Exception as e:
        print(f"Error writing video file: {e}")
        sys.exit(1)

def find_newest_json():
    cwd = os.getcwd()
    ready_dir = os.path.join(cwd, 'ready')
    if not os.path.isdir(ready_dir):
        return None
    jsons = [os.path.join(ready_dir, f) for f in os.listdir(ready_dir) if f.endswith('.json')]
    return max(jsons, key=os.path.getmtime) if jsons else None

def main():
    parser = argparse.ArgumentParser(description='Overlay text and update JSON final_video.')
    parser.add_argument('--input_video', help='Path to input video.')
    parser.add_argument('--output_video', help='Path to output video.')
    parser.add_argument('--start_text', default='', help='Text for start overlay.')
    parser.add_argument('--end_text', default='', help='Text for end overlay.')
    parser.add_argument('--start_duration', type=float, default=5.0, help='Duration for start overlay.')
    parser.add_argument('--end_duration', type=float, default=5.0, help='Duration for end overlay.')
    parser.add_argument('--start_font_path', default='', help='Font path for start overlay.')
    parser.add_argument('--end_font_path', default='', help='Font path for end overlay.')
    parser.add_argument('--start_fontsize', type=int, default=75, help='Font size for start overlay.')
    parser.add_argument('--end_fontsize', type=int, default=75, help='Font size for end overlay.')
    parser.add_argument('--text_color', default='white', help='Text color.')
    parser.add_argument('--bg_color', nargs=3, type=int, default=[0,0,0], help='Background color RGB.')
    parser.add_argument('--col_opacity', type=float, default=0.3, help='Background opacity.')
    parser.add_argument('--padding', type=int, default=5, help='Padding around text.')
    parser.add_argument('--fade_in', action='store_true', help='Enable fade-in.')
    parser.add_argument('--fade_out', action='store_true', help='Enable fade-out.')
    parser.add_argument('--fade_duration', type=float, default=1.0, help='Fade duration.')
    parser.add_argument('--position', nargs=2, type=int, metavar=('X','Y'), help='Overlay position.')
    parser.add_argument('json_file', nargs='?', help='Optional workflow JSON to update.')
    args = parser.parse_args()

    json_path = args.json_file or find_newest_json()

    config = {}
    if json_path and os.path.isfile(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

    if args.input_video and args.output_video:
        inp = args.input_video
        out = args.output_video
    else:
        vid_cfg = config.get('video', {})
        inp = vid_cfg.get('input') or vid_cfg.get('video') or vid_cfg.get('video_path') or config.get('final_video')
        out = vid_cfg.get('output') or vid_cfg.get('overlay_output')
        if not inp or not out:
            print("Error: video input/output not specified.")
            sys.exit(1)

    start_text = args.start_text if args.start_text else config.get('reference', '')
    end_text = args.end_text if args.end_text else config.get('overlays', {}).get('end', {}).get('text', '')
    start_duration = args.start_duration or config.get('overlays', {}).get('start', {}).get('duration', 5)
    end_duration = args.end_duration or config.get('overlays', {}).get('end', {}).get('duration', 5)
    start_font = args.start_font_path or config.get('overlays', {}).get('start', {}).get('font_file', '')
    end_font = args.end_font_path or config.get('overlays', {}).get('end', {}).get('font_file', '')
    start_fs = args.start_fontsize or config.get('overlays', {}).get('start', {}).get('fontsize', 75)
    end_fs = args.end_fontsize or config.get('overlays', {}).get('end', {}).get('fontsize', 75)
    text_color = args.text_color or config.get('overlays', {}).get('start', {}).get('text_color', 'white')
    bg_color = tuple(args.bg_color) or tuple(config.get('overlays', {}).get('start', {}).get('bg_color', [0,0,0]))
    col_opacity = args.col_opacity or config.get('overlays', {}).get('start', {}).get('col_opacity', 0.3)
    padding = args.padding or config.get('overlays', {}).get('start', {}).get('padding', 5)
    fade_in = args.fade_in if args.fade_in else config.get('overlays', {}).get('start', {}).get('fade_in', True)
    fade_out = args.fade_out if args.fade_out else config.get('overlays', {}).get('end', {}).get('fade_out', True)
    fade_duration = args.fade_duration or config.get('overlays', {}).get('start', {}).get('fade_duration', 1)
    position = tuple(args.position) if args.position else None

    add_text_overlay(
        inp, out,
        start_text, end_text,
        start_duration, end_duration,
        start_font, end_font,
        start_fs, end_fs,
        text_color, bg_color, col_opacity, padding,
        fade_in, fade_out, fade_duration,
        position
    )

    if json_path:
        config['overlay_video'] = os.path.abspath(out)
        config['final_video'] = os.path.abspath(out)
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            print(f"Updated JSON with final_video: {config['final_video']}")
        except Exception as e:
            print(f"Error updating JSON: {e}")

if __name__ == "__main__":
    main()