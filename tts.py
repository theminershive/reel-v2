import os
import json
import requests
from dotenv import load_dotenv
from pathlib import Path
from config import tts_default_speaker, tts_default_language

# Load environment variables
load_dotenv()

# Constants
LOCAL_TTS_URL = os.getenv("LOCAL_TTS_URL", "http://192.168.1.154:5500")
AUDIO_DIR = Path("audio")
AUDIO_DIR.mkdir(exist_ok=True)
CHUNK_SIZE = 1024


def generate_tts_local(narration_text, audio_path, speaker=None, language=None):
    """
    Generate TTS audio using a local OpenTTS server and save it to a file.
    """
    url = f"{LOCAL_TTS_URL}/synthesize"
    # Use default speaker/language if not provided
    _speaker = speaker or tts_default_speaker
    _language = language or tts_default_language
    # Build payload
    payload = {
        "text": narration_text,
        "speaker": _speaker
    }
    if _language:
        payload["language"] = _language
    headers = {"Content-Type": "application/json"}

    

    response = requests.post(url, json=payload, headers=headers, stream=True)
    if response.status_code == 200:
        with open(audio_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
        print(f"Audio content saved to {audio_path}")
        return True
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return False


def process_tts(script_data, audio_dir=AUDIO_DIR):
    """
    Process the script JSON, generate audio for each narration segment,
    and update the JSON with audio paths.
    """
    sections = script_data.get("sections", [])
    # Optional speaker and language settings at top level
    speaker = script_data.get("speaker")
    language = script_data.get("language")

    for section_idx, section in enumerate(sections, start=1):
        segments = section.get("segments", [])
        if not segments:
            print(f"Section {section_idx} has no segments. Skipping.")
            continue

        for segment_idx, segment in enumerate(segments, start=1):
            narration = segment.get("narration", {})
            text = narration.get("text", "")

            if not text:
                print(f"Section {section_idx}, Segment {segment_idx} has no narration text. Skipping.")
                continue

            print(f"Generating TTS for Section {section_idx}, Segment {segment_idx}: {text}")

            # Save as WAV for compatibility with OpenTTS output
            audio_filename = f"section_{section_idx}_segment_{segment_idx}.wav"
            audio_path = audio_dir / audio_filename

            success = generate_tts_local(text, audio_path, speaker=speaker, language=language)
            segment.setdefault("narration", {})["audio_path"] = str(audio_path) if success else None

    return script_data


def save_audio_paths(updated_script, filename="video_script_with_audio.json"):
    """
    Save the updated script JSON with audio paths to a file.
    """
    script_path = Path(filename)
    try:
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(updated_script, f, indent=4)
        print(f"Updated script with audio paths saved to {script_path}")
        return script_path
    except Exception as e:
        print(f"Error saving updated script: {e}")
        return None


def load_script_from_json(json_path):
    """
    Load script data from a specified JSON file.
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to load JSON file: {e}")
        return None


if __name__ == "__main__":
    json_path = input("Enter the path to the JSON file to use: ").strip()
    if not os.path.exists(json_path):
        print(f"The specified JSON file does not exist: {json_path}")
    else:
        script_data = load_script_from_json(json_path)
        if script_data:
            updated_script = process_tts(script_data)
            if updated_script:
                save_audio_paths(updated_script)