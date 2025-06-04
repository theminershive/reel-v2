import math
import openai
import json
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from openai.error import OpenAIError
import random
import re
from video_assembler import search_sounds, is_banned

from voices_and_styles import VOICES, MODELS

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Constants
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VIDEO_SCRIPTS_DIR = "./output/video_scripts/"
MAX_SCRIPT_TOKENS = 32000

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set. Check your .env file.")
    exit(1)
openai.api_key = OPENAI_API_KEY
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")


def generate_background_music(length):
    music_types = ["cinematic", "ambient", "suspense", "upbeat", "melodic", "neutral", "inspiring", "dramatic"]
    selected = random.sample(music_types, 2) if length > 120 else random.sample(music_types, 1)
    logger.debug(f"Selected background music: {selected}")
    return ", ".join(selected)


def generate_transition_effect():
    transition_effects = ["swoosh", "fade-in", "whoosh", "glimmer"]
    effect = random.choice(transition_effects)
    logger.debug(f"Selected transition effect: {effect}")
    return effect


def call_openai_api_generate_script(prompt, max_tokens, temperature):
    try:
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are ChatGPT, a large language model trained by OpenAI."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )
        logger.debug("OpenAI API call for script generation successful.")
        return response
    except OpenAIError as e:
        logger.error(f"OpenAI API error during script generation: {e}")
        return None


def calculate_max_tokens(length):
    return 8000


def select_background_music_via_gpt(topic, music_options):
    try:
        return random.choice(music_options)
    except Exception:
        return "neutral"


def generate_video_script(
    topic,
    length,
    size,
    num_sections,
    num_segments,
    voice=None,
    style=None,
    prompt_template=None,
):
    try:
        TARGET_MAIN_SEGMENT_DURATION = 4
        TARGET_SEGUE_SEGMENT_DURATION = 2
        MIN_SEGMENT_DURATION = 3
        MAX_SEGMENT_DURATION = 5

        total_main_segments = num_sections * num_segments
        num_segue_sections = max(0, num_sections - 1)

        total_segue_time = num_segue_sections * TARGET_SEGUE_SEGMENT_DURATION
        total_main_time = max(0, length - total_segue_time)

        if total_main_segments > 0:
            raw_main_segment_duration = total_main_time / total_main_segments
        else:
            raw_main_segment_duration = TARGET_MAIN_SEGMENT_DURATION

        main_segment_duration = max(MIN_SEGMENT_DURATION, min(MAX_SEGMENT_DURATION, int(raw_main_segment_duration)))

        logger.debug(f"Main segment duration: {main_segment_duration} seconds")
        logger.debug(f"Segue segment duration: {TARGET_SEGUE_SEGMENT_DURATION} seconds")

        sections = []

        # Main sections
        for i in range(num_sections):
            section_number = i + 1
            section = {
                "section_number": section_number,
                "title": f"Section {section_number}",
                "section_duration": num_segments * main_segment_duration,
                "segments": []
            }
            for j in range(num_segments):
                global_index = i * num_segments + j
                segment = {
                    "segment_number": j + 1,
                    "narration": {
                        "text": "Narration text here.",
                        "start_time": global_index * main_segment_duration,
                        "duration": main_segment_duration
                    },
                    "visual": {
                        "type": "image",
                        "prompt": f"Visual prompt for {topic}",
                        "start_time": global_index * main_segment_duration,
                        "duration": main_segment_duration
                    },
                    "sound": {
                        "transition_effect": generate_transition_effect()
                    }
                }
                section["segments"].append(segment)
            sections.append(section)

            if i < num_sections - 1:
                segue = {
                    "section_number": section_number + 0.5,
                    "title": "Segue",
                    "section_duration": TARGET_SEGUE_SEGMENT_DURATION,
                    "segments": [{
                        "segment_number": 1,
                        "narration": {"text": "", "start_time": section_number * main_segment_duration, "duration": TARGET_SEGUE_SEGMENT_DURATION},
                        "visual": {"type": "image", "prompt": "", "start_time": section_number * main_segment_duration, "duration": TARGET_SEGUE_SEGMENT_DURATION},
                        "sound": {"transition_effect": generate_transition_effect()}
                    }]
                }
                sections.append(segue)

        # Load and format JSON template
        skeleton_path = os.path.join(os.path.dirname(__file__), 'script_json_template.json')
        with open(skeleton_path, 'r') as skeleton_file:
            filled = skeleton_file.read().format(video_size=size, use_transitions='true', use_background_music='true')
        script_json = json.loads(filled)
        script_json['sections'] = sections

        if length > 10:
            script_json['social_media'] = {
                "title": "Suggested title",
                "description": "Engaging description.",
                "tags": ["tag1", "tag2", "tag3"]
            }

        prompt_json = json.dumps(script_json, indent=4)

        if prompt_template:
            template = prompt_template
        else:
            template_path = os.path.join(os.path.dirname(__file__), 'prompt_template.txt')
            with open(template_path, 'r') as template_file:
                template = template_file.read()
        prompt = template.format(length=length, topic=topic, prompt_json=prompt_json,
                                 num_sections=num_sections, num_segments=num_segments)

        response = call_openai_api_generate_script(prompt, MAX_SCRIPT_TOKENS, 0.9)
        if not response:
            logger.error("Failed to retrieve video script.")
            return None

        content = response.choices[0].message['content'].strip()
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        start = content.find('{')
        end = content.rfind('}')
        content = content[start:end+1] if start != -1 and end != -1 else content
        content = re.sub(r',\s*([\]}])', r'\1', content)
        script_data = json.loads(content)

        for sec in script_data.get('sections', []):
            for seg in sec.get('segments', []):
                seg.setdefault('sound', {})['transition_effect'] = seg['sound'].get('transition_effect', generate_transition_effect())

        combined = ' '.join(seg['narration']['text'] for sec in script_data['sections'] for seg in sec.get('segments', []))
        if voice:
            script_data['tone'] = voice
        else:
            script_data['tone'] = select_voice(combined)

        if style:
            script_data['image_style'] = style
            info = MODELS.get(style, {})
        else:
            style, info = select_style(combined)
            script_data['image_style'] = style
        bg = select_background_music_via_gpt(topic, ["cinematic","ambient","suspense","upbeat","melodic","neutral","inspiring","dramatic"])
        script_data['background_music'] = bg
        script_data['background_music_type'] = bg

        safe = re.sub(r'[^A-Za-z0-9]+', '_', topic)[:50]
        outdir = os.getenv('VIDEO_OUTPUT_DIR', './output/final')
        script_data['raw_video'] = os.path.join(outdir, f"{safe}_raw.mp4")
        script_data['final_video'] = os.path.join(outdir, f"{safe}.mp4")
        script_data['topic'] = topic
        return script_data
    except Exception as e:
        logger.error(f"Unhandled error: {e}")

# Note: select_voice, select_style, save_script, main() remain unchanged from prior implementation.

def select_voice(script_text):
    """
    Selects the most appropriate voice from the VOICES dictionary based on the complete script.

    Args:
        script_text (str): The complete narration text of the script.

    Returns:
        str: The name of the selected voice.
    """
    # Prepare the voice options information
    voice_options = "\n".join([
        f"- **{voice_name}**: {voice_info['description']}"
        for voice_name, voice_info in VOICES.items()
    ])

    prompt = f"""
Given the following script narration:

\"\"\"
{script_text}
\"\"\"

And the following list of available voices:

{voice_options}

Please analyze the script and select the most appropriate voice for the narration from the list above.

**Instructions:**
- Choose the voice that best matches the script's content and tone.
- Provide only the name of the selected voice without any additional text.
    """

    try:
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are ChatGPT, an assistant that selects the most appropriate narration voice based on script content and provided voice options."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=10,
            temperature=0.0  # Ensures consistent and deterministic output
        )

        selected_voice = response.choices[0].message['content'].strip()
        logger.debug(f"Selected voice by GPT: {selected_voice}")

        # Validate the selected voice
        if selected_voice in VOICES:
            return selected_voice
        else:
            logger.warning(f"GPT selected an unknown voice: '{selected_voice}'. Defaulting to 'Frederick Surrey'.")
            return "Frederick Surrey"

    except OpenAIError as e:
        logger.error(f"OpenAI API error during voice selection: {e}")
        # Default voice in case of error
        return "Frederick Surrey"
    except Exception as e:
        logger.error(f"An unexpected error occurred during voice selection: {e}")
        # Default voice in case of error
        return "Frederick Surrey"

def select_style(script_text):
    """
    Selects the most appropriate style by sending the script back to GPT along with the style list.
    Args:
        script_text (str): The entire script narration.
    Returns:
        tuple: Selected style name and its corresponding model info.
    """
    # Construct the styles description
    styles_description = "\n".join([
        f"- **{style_name}**: {info['description']} Keywords: {', '.join(info['keywords'])}"
        for style_name, info in MODELS.items()
    ])

    prompt = f"""
Given the following video script narration:

\"\"\"
{script_text}
\"\"\"

And the following list of styles:

{styles_description}

Please analyze the script narration and select the most appropriate style from the list above that best matches the content and tone of the script. Provide only the name of the selected style.
    """

    # Call the OpenAI API
    try:
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.3  # Lower temperature for consistency
        )

        selected_style = response.choices[0].message['content'].strip()
        logger.debug(f"Selected style from GPT:\n{selected_style}")

        # Validate the selected style
        if selected_style in MODELS:
            model_info = MODELS[selected_style]
            return selected_style, model_info
        else:
            logger.error(f"GPT returned an unknown style: {selected_style}. Selecting a random style.")
            selected_style = random.choice(list(MODELS.keys()))
            model_info = MODELS[selected_style]
            return selected_style, model_info

    except OpenAIError as e:
        logger.error(f"OpenAI API error during style selection: {e}")
        # In case of error, select a random style
        selected_style = random.choice(list(MODELS.keys()))
        model_info = MODELS[selected_style]
        return selected_style, model_info

    except Exception as e:
        logger.error(f"An unexpected error occurred during style selection: {e}")
        selected_style = random.choice(list(MODELS.keys()))
        model_info = MODELS[selected_style]
        return selected_style, model_info

def save_script(script_data, tone, style, topic, filename=None):
    """
    Saves the generated script, tone, and style to a JSON file.
    Args:
        script_data (dict): The generated script data.
        tone (str): The name of the selected voice.
        style (str): The selected style name (optional).
        topic (str): The topic of the video.
        filename (str, optional): The filename for the saved script. Defaults to None.
    Returns:
        str: The path to the saved script file.
    """
    if not filename:
        # Replace any invalid filename characters
        safe_topic = re.sub(r'[\\/*?:"<>|]', "", topic)
        filename = f"{safe_topic.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    script_path = os.path.join(VIDEO_SCRIPTS_DIR, filename)

    # Ensure the directory exists
    os.makedirs(VIDEO_SCRIPTS_DIR, exist_ok=True)

    # Add tone and style to the script data
    script_data["tone"] = tone
    if style:
        script_data["settings"]["image_generation_style"] = style
        script_data["settings"]["style_selection_reason"] = f"The {style} style was selected based on the script content."

    try:
        with open(script_path, 'w', encoding='utf-8') as f:
            json.dump(script_data, f, indent=4)
        logger.info(f"Script, tone, and style saved to {script_path}")
        return script_path
    except Exception as e:
        logger.error(f"An error occurred while saving the script: {e}")
        return None

def select_voice_and_style(script_text):
    """
    Selects the most appropriate voice and style based on the complete script.

    Args:
        script_text (str): The complete narration text of the script.

    Returns:
        tuple: Selected voice name, selected style name, and style info.
    """
    selected_voice = select_voice(script_text)
    selected_style, style_info = select_style(script_text)
    return selected_voice, selected_style, style_info

def main():
    """
    Main function to generate, select voice and style, update visuals, and save a video script.
    """
    try:
        # Gather user inputs
        topic = input("Enter the topic of the video: ").strip()
        length_input = input("Enter the length of the video in seconds: ").strip()
        size = input("Enter the size of the video (e.g., 1080x1920): ").strip()
        num_sections_input = input("Enter the number of sections: ").strip()
        num_segments_input = input("Enter the number of segments per section: ").strip()

        # Validate numeric inputs
        try:
            length = int(length_input)
            num_sections = int(num_sections_input)
            num_segments = int(num_segments_input)
        except ValueError:
            logger.error("Invalid input. Length, number of sections, and number of segments must be integers.")
            print("Invalid input. Please ensure that length, number of sections, and number of segments are numbers.")
            return

        # Adjust MAX_SCRIPT_TOKENS based on video length
        global MAX_SCRIPT_TOKENS
        MAX_SCRIPT_TOKENS = calculate_max_tokens(length)
        logger.debug(f"Adjusted MAX_SCRIPT_TOKENS based on video length: {MAX_SCRIPT_TOKENS}")

        # Generate the video script
        script_data = generate_video_script(topic, length, size, num_sections, num_segments)

        if not script_data:
            print("Failed to generate the script. Please check the logs for more details.")
            return

        # Combine all narration texts for voice and style selection
        narration_texts = []
        for section in script_data.get("sections", []):
            if "segments" in section:
                for segment in section["segments"]:
                    narration_text = segment.get("narration", {}).get("text", "")
                    if narration_text:
                        narration_texts.append(narration_text)
            else:
                narration_text = section.get("narration", {}).get("text", "")
                if narration_text:
                    narration_texts.append(narration_text)

        combined_narration = " ".join(narration_texts)
        logger.debug(f"Combined narration text for voice and style selection:\n{combined_narration}")

        # Select the appropriate voice and style based on the combined narration
        selected_voice, selected_style, style_info = select_voice_and_style(combined_narration)
        logger.info(f"Selected voice: {selected_voice}")
        logger.info(f"Selected style: {selected_style}")

        # Update the visual prompts based on the selected style
        from visuals_and_social import update_visual_prompts
        update_visual_prompts(script_data, style_info)

        # Save the script with tone (voice) and style information
        saved_path = save_script(script_data, selected_voice, selected_style, topic)

        if saved_path:
            print(f"Script generation, voice and style selection, and saving completed successfully.\nSaved to: {saved_path}")
        else:
            print("Script generated, but failed to save the file.")

    except Exception as e:
        logger.error(f"An unexpected error occurred in the main function: {e}")
        print("An unexpected error occurred. Please check the logs for more details.")

if __name__ == '__main__':
    main()
