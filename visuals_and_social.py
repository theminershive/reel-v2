import os
import json
import re
import logging
from dotenv import load_dotenv
import openai
from openai.error import OpenAIError
from narration_and_style import select_voice, select_style
from voices_and_styles import MODELS

# Load environment variables
load_dotenv()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

#  Sanitization rules 
FILTER_KEYWORDS = {
    # Minors / age-sensitive
    r"\bchild\b": "figure",
    r"\bchildren\b": "figures",
    r"\bkid\b": "person",
    r"\bminor\b": "individual",
    r"\binfant\b": "figure",
    r"\btoddler\b": "person",
    r"\bbaby\b": "person",
    r"\bteen\b": "young person",
    r"\bteenager\b": "young person",
    r"\byouth\b": "individual",
    r"\bjuvenile\b": "individual",
    r"\bunderage\b": "young individual",
    r"\bchildlike\b": "figurative",
    r"\blittle\s+girl\b": "young person",
    r"\blittle\s+boy\b": "young person",

    # Celebrity / identity
    r"\bcelebrity\b": "figure",
    r"\bfamous\b": "well-known",
    r"\bpublic\s+figure\b": "figure",

    # Genitals – masculine
    r"\bpenis\b": "anatomical part",
    r"\bcock\b": "anatomical part",
    r"\bdick\b": "anatomical part",
    r"\bshaft\b": "anatomical part",
    r"\btesticle\b": "anatomical part",
    r"\btesticles\b": "anatomical parts",
    r"\bscrotum\b": "anatomical part",

    # Genitals – feminine
    r"\bvagina\b": "anatomical part",
    r"\bvulva\b": "anatomical part",
    r"\blabia\b": "anatomical parts",
    r"\bclitoris\b": "anatomical part",
    r"\bpussy\b": "anatomical part",

    # Breasts / chest
    r"\bbreast\b": "anatomical part",
    r"\bbreasts\b": "anatomical parts",
    r"\bboob\b": "anatomical part",
    r"\bboobs\b": "anatomical parts",
    r"\btit\b": "anatomical part",
    r"\btits\b": "anatomical parts",
    r"\bnipple\b": "anatomical part",
    r"\bnipples\b": "anatomical parts",

    # Buttocks / anus
    r"\bbutt\b": "anatomical part",
    r"\bbuttocks\b": "anatomical parts",
    r"\bass\b": "anatomical part",
    r"\banus\b": "anatomical part",
    r"\basshole\b": "anatomical part",

    # Sexual fluids / arousal
    r"\bcum\b": "fluid",
    r"\bsemen\b": "fluid",
    r"\bsperm\b": "fluid",
    r"\bmilf\b": "individual",
    r"\borgasm\b": "reaction",
    r"\barousal\b": "reaction",

    # Sexual acts / slang
    r"\bsex\b": "intimacy",
    r"\bsexual\b": "intimate",
    r"\bfuck\b": "act",
    r"\bfucking\b": "act",
    r"\bintercourse\b": "act",
    r"\bpenetration\b": "act",
    r"\bmasturbat(e|ion|ing)\b": "act",
    r"\bjerk\s*off\b": "act",
    r"\bhandjob\b": "act",
    r"\bblowjob\b": "act",
    r"\bsuck\b": "act",
    r"\bgrope\b": "act",
    r"\bstrip(per|ping)\b": "act",
    r"\bbukkake\b": "act",

    # Illegal / extreme content
    r"\bcp\b": "content",
    r"\bchild\s*porn\b": "content",
    r"\bincest\b": "content",
    r"\brape\b": "act",
    r"\bbeastiality\b": "content",
    r"\bzoophilia\b": "content",

    # Violence / gore (optional – helps reduce graphic prompts)
    r"\bgore\b": "graphic",
    r"\bblood\b": "liquid",
    r"\bbleeding\b": "graphic",
    r"\bviolent\b": "aggressive",
}

def sanitize_prompt(prompt: str) -> str:
    """
    Replace any forbidden keywords in the prompt
    with neutral alternatives before sending it on.
    """
    sanitized = prompt
    for pattern, replacement in FILTER_KEYWORDS.items():
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized

def update_visual_prompts(script_data, style_info):
    """
    Updates the visual prompts in the script data based on the selected style.
    Args:
        script_data (dict): The script data containing sections and segments.
        style_info (dict): The selected style information from MODELS.
    """
    style_description = style_info["description"]
    example_prompts = "\n".join(style_info["example_prompts"])

    for section in script_data.get("sections", []):
        # For sections with segments
        if "segments" in section:
            for segment in section["segments"]:
                narration_text = segment["narration"].get("text", "")
                if not narration_text:
                    continue
                # Generate new visual prompt
                prompt = f"""
Given the following narration text:

\"\"\"{narration_text}\"\"\"

And the following style description:

{style_description}

With these example prompts:

{example_prompts}

Generate a detailed visual prompt that complements the narration and adheres to the style guidelines.

Provide only the visual prompt text without any additional explanations.
                """

                try:
                    response = openai.ChatCompletion.create(
                        model=OPENAI_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=70,
                        temperature=0.9
                    )
                    visual_prompt = response.choices[0].message['content'].strip()
                    visual_prompt = sanitize_prompt(visual_prompt)  # <-- Sanitizing here
                    logger.debug(f"Generated visual prompt:\n{visual_prompt}")
                    segment["visual"]["prompt"] = visual_prompt
                except OpenAIError as e:
                    logger.error(f"OpenAI API error during visual prompt generation: {e}")
                except Exception as e:
                    logger.error(f"An unexpected error occurred during visual prompt generation: {e}")
        else:
            # For sections without segments (short videos)
            narration_text = section.get("narration", {}).get("text", "")
            if not narration_text:
                continue
            # Generate new visual prompt
            prompt = f"""
Given the following narration text:

\"\"\"{narration_text}\"\"\"

And the following style description:

{style_description}

With these example prompts:

{example_prompts}

Generate a detailed visual prompt that complements the narration and adheres to the style guidelines.

Provide only the visual prompt text without any additional explanations.
            """

            try:
                response = openai.ChatCompletion.create(
                    model=OPENAI_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=70,
                    temperature=0.9
                )
                visual_prompt = response.choices[0].message['content'].strip()
                visual_prompt = sanitize_prompt(visual_prompt)  # <-- Sanitizing here
                logger.debug(f"Generated visual prompt:\n{visual_prompt}")
                section["visual"]["prompt"] = visual_prompt
            except OpenAIError as e:
                logger.error(f"OpenAI API error during visual prompt generation: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred during visual prompt generation: {e}")


def generate_social_media(script_data):
    """
    Generates a social media post (title, description, tags) based on the script.
    """
    try:
        prompt = f"""
Based on the following video script JSON, generate a social media post JSON with fields:
- "title": Catchy title for the post.
- "description": Engaging description optimized for SEO with around 1000 characters.
- "tags": List of 5 to 10 relevant hashtags.

Script JSON:
{json.dumps(script_data, indent=4)}
"""
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are an assistant that creates social media posts from video scripts."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        content = response.choices[0].message['content']
        # Clean markdown fences
        clean = re.sub(r'^```(?:json)?\s*', '', content.strip())
        clean = re.sub(r'\s*```$', '', clean)
        return json.loads(clean)
    except Exception as e:
        logger.error(f"Error generating social media: {e}")
        return {
            "title": "New Video Release!",
            "description": "Check out our latest video now!",
            "tags": ["video", "release", "AI", "shorts"]
        }

import json
import argparse
import logging
from narration_and_style import select_voice, select_style
from voices_and_styles import MODELS

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

def enrich_script(script_data):
    """
    Enhances the script_data with:
    - Tone (voice) selection
    - Style selection
    - Visual prompt sanitization
    - Visual updates
    - Social media post generation
    """
    # 1) Select tone
    full_text = " ".join(
        seg.get("narration", {}).get("text", "")
        for sec in script_data.get("sections", [])
        for seg in sec.get("segments", [])
    )
    tone = select_voice(full_text)
    script_data["tone"] = tone

    # 2) Select style
    style_name, style_info = select_style(full_text)
    script_data["settings"]["image_generation_style"] = style_name
    script_data["settings"]["style_selection_reason"] = f"The {style_name} style was selected based on the script content."

    # 3) Sanitize any manually-added raw prompts (rare)
    for sec_idx, section in enumerate(script_data.get("sections", []), start=1):
        for seg_idx, seg in enumerate(section.get("segments", []), start=1):
            raw = seg.get("visual_prompt")
            if raw:
                safe = sanitize_prompt(raw)
                if raw != safe:
                    logger.info(f"Sanitized visual prompt (section {sec_idx}, seg {seg_idx}): {safe!r}")
                seg["visual_prompt"] = safe

    # 4) Generate updated visual prompts via OpenAI
    update_visual_prompts(script_data, style_info)

    # 5) Generate social media post
    script_data["social_media"] = generate_social_media(script_data)

    return script_data

def main():
    parser = argparse.ArgumentParser(description="Enhance a script JSON with visuals and metadata.")
    parser.add_argument("input_json", help="Path to the input script JSON file")
    parser.add_argument("output_json", help="Path to the output JSON file to save")

    args = parser.parse_args()

    try:
        with open(args.input_json, "r", encoding="utf-8") as infile:
            script_data = json.load(infile)

        logger.info("Enhancing script...")
        enhanced_script = enrich_script(script_data)

        with open(args.output_json, "w", encoding="utf-8") as outfile:
            json.dump(enhanced_script, outfile, indent=4, ensure_ascii=False)

        logger.info(f"Saved enriched script to {args.output_json}")
    except Exception as e:
        logger.error(f"Error processing script: {e}")

if __name__ == "__main__":
    main()
