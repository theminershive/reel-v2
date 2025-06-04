import openai
import os
import json
import re
import difflib
import datetime
from dotenv import load_dotenv
import logging

# --------------------------------------------------
# ENVIRONMENT
# --------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError("OPENAI_API_KEY not found in environment or .env file.")

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")  # default to ChatGPT-4o
openai.api_key = OPENAI_API_KEY

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
HISTORY_FILE = "topics_history.json"
SIMILARITY_THRESHOLD = 0.7   # Sequence similarity for near-duplicate detection
TOKEN_OVERLAP_THRESHOLD = 3  # Minimum keyword overlap to consider duplicates
STOPWORDS = {"the","of","and","a","an","to","in","on","for","with","without","new","?","!",":"}

CURRENT_YEAR = datetime.datetime.now().year
NEXT_YEAR = CURRENT_YEAR + 1

# --------------------------------------------------
# HISTORY UTILITIES
# --------------------------------------------------

def load_history():
    """Return a normalised list of {date,title} dicts."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        raw = json.load(open(HISTORY_FILE, "r"))
    except Exception:
        return []

    # Normalise
    if isinstance(raw, dict) and "title" in raw:
        raw = [raw]
    elif isinstance(raw, str):
        raw = [{"date": today, "title": raw}]
    elif not isinstance(raw, list):
        return []

    normalised = []
    for entry in raw:
        if isinstance(entry, str):
            normalised.append({"date": today, "title": entry})
        elif isinstance(entry, dict) and "title" in entry:
            normalised.append({
                "date": entry.get("date", today),
                "title": entry["title"],
            })
    return normalised


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

# --------------------------------------------------
# TEXT SIMILARITY
# --------------------------------------------------

def extract_keywords(text: str) -> set[str]:
    tokens = re.findall(r"\w+", text.lower())
    return {tok for tok in tokens if tok not in STOPWORDS}


def titles_too_similar(a: str, b: str) -> bool:
    kw_a, kw_b = extract_keywords(a), extract_keywords(b)
    overlap = len(kw_a & kw_b)
    ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return overlap >= TOKEN_OVERLAP_THRESHOLD and ratio >= SIMILARITY_THRESHOLD

# --------------------------------------------------
# PROMPT
# --------------------------------------------------
SYSTEM_PROMPT = f"""
You are an expert at crafting loopable, curiosity-driven short-form video topics — ideal for TikTok, Instagram Reels, and YouTube Shorts.

Generate FIVE concise, punchy topic ideas designed to be narrated in under 30 seconds and to loop seamlessly. Each topic should spark curiosity with a wild fact, paradox, or thought experiment, phrased as a standalone question or statement.

Rules:
- Each topic must be a single sentence of no more than 12 words.
- Use open-ended phrasing to avoid finality and ensure smooth looping.
- Inspire wonder, unease, or intrigue without revealing the answer.
- Focus on mind-bending scenarios, paradoxes, or mysterious possibilities.

Output format (one per line):
Topic: <topic>

Example styles:
- “What if gravity reversed for just one minute?”
- “The paradox of a sentence that reads itself.”
- “What if your reflection decided to not mimic you?”
"""

# --------------------------------------------------
# OUTPUT PARSER
# --------------------------------------------------
def parse_suggestions(raw: str) -> list[dict]:
    tpl = {"title": "", "hashtags": "", "description": "", "subject": "None", "extrainfo": "None"}
    suggestions, current = [], tpl.copy()
    for line in raw.splitlines():
        if line.startswith("Topic:"):
            suggestions.append({"topic": line.removeprefix("Topic:").strip()})
    return suggestions

# --------------------------------------------------
# MAIN PIPELINE
# --------------------------------------------------
def generate_loopable_topics() -> None:
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    history = load_history()
    used_today = [h["title"] for h in history if h["date"] == today_str]

    user_msg = (
        f"Generate five loopable topics. Avoid: {', '.join(used_today) if used_today else 'None'}."
    )

    response = openai.ChatCompletion.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.8,
        max_tokens=200,
    )

    raw = response["choices"][0]["message"]["content"]
    print("--- RAW GPT OUTPUT ---\n" + raw)

    suggestions = parse_suggestions(raw)

    # de-duplicate
    unique = []
    for sug in suggestions:
        if not any(titles_too_similar(sug["topic"], u["topic"]) for u in unique):
            unique.append(sug)

    # save history entries
    for sug in unique:
        history.append({"date": today_str, "title": sug["topic"]})
    save_history(history)

    # output final list
    print(json.dumps({"topics": [s["topic"] for s in unique]}, indent=4))

if __name__ == "__main__":
    generate_loopable_topics()
