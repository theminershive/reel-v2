import openai
import os
import json
import re
import difflib
import datetime
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment and OpenAI key
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError("OPENAI_API_KEY not found in environment or .env file.")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
openai.api_key = OPENAI_API_KEY

# Constants
HISTORY_FILE = "topics_history.json"
SIMILARITY_THRESHOLD = 0.7
TOKEN_OVERLAP_THRESHOLD = 3
STOPWORDS = {"the", "of", "and", "a", "an", "to", "in", "on", "for", "with", "without", "new", "?", "!", ":"}
PROMPT_FILE = os.getenv("TOPIC_PROMPT_FILE", "topic_prompt.txt")


def load_system_prompt(custom_prompt: str | None = None) -> str:
    """Return the system prompt text."""
    if custom_prompt is not None:
        return custom_prompt
    try:
        with open(PROMPT_FILE, "r") as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt file '{PROMPT_FILE}' not found.")

SYSTEM_PROMPT = load_system_prompt()

# Load topic history
def load_history():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        raw = json.load(open(HISTORY_FILE, "r"))
    except Exception:
        return []
    if isinstance(raw, dict) and "title" in raw:
        raw = [raw]
    elif isinstance(raw, str):
        raw = [{"date": today, "title": raw}]
    elif not isinstance(raw, list):
        return []
    normalized = []
    for entry in raw:
        if isinstance(entry, str):
            normalized.append({"date": today, "title": entry})
        elif isinstance(entry, dict) and "title" in entry:
            normalized.append({
                "date": entry.get("date", today),
                "title": entry["title"],
            })
    return normalized

# Save history back to disk
def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

# Keyword extraction
def extract_keywords(text: str) -> set[str]:
    tokens = re.findall(r"\w+", text.lower())
    return {tok for tok in tokens if tok not in STOPWORDS}

# Similarity check
def titles_too_similar(a: str, b: str) -> bool:
    kw_a, kw_b = extract_keywords(a), extract_keywords(b)
    overlap = len(kw_a & kw_b)
    ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return overlap >= TOKEN_OVERLAP_THRESHOLD and ratio >= SIMILARITY_THRESHOLD

# Parse GPT suggestions with regex
def parse_suggestions(raw: str) -> list[dict]:
    tpl = {"title": "", "hashtags": "", "description": "", "subject": "None", "extrainfo": "None", "length": None, "sections": None, "segments_per_section": None}
    suggestions, current = [], tpl.copy()
    for line in raw.splitlines():
        # Match numbered or plain Title:
        m = re.match(r'^\s*(?:\d+\.\s*)?Title:\s*(.*)', line)
        if m:
            if current["title"]:
                suggestions.append(current)
                current = tpl.copy()
            current["title"] = m.group(1).strip()
            continue
        m = re.match(r'^\s*(?:\d+\.\s*)?Hashtags:\s*(.*)', line)
        if m:
            current["hashtags"] = m.group(1).strip()
            continue
        m = re.match(r'^\s*(?:\d+\.\s*)?Description:\s*(.*)', line)
        if m:
            current["description"] = m.group(1).strip()
            continue
        m = re.match(r'^\s*Source:\s*(.*)', line)
        if m:
            current["subject"] = m.group(1).strip()
            continue
        m = re.match(r'^\s*ExtraInfo:\s*(.*)', line)
        if m:
            current["extrainfo"] = m.group(1).strip()
            continue
        m = re.match(r'^\s*Length:\s*(\d+)', line)
        if m:
            current["length"] = int(m.group(1))
            continue
        m = re.match(r'^\s*Sections:\s*(\d+)', line)
        if m:
            current["sections"] = int(m.group(1))
            continue
        m = re.match(r'^\s*SegmentsPerSection:\s*(\d+)', line)
        if m:
            current["segments_per_section"] = int(m.group(1))
            continue
    if current["title"]:
        suggestions.append(current)
    # Fallback defaults
    for s in suggestions:
        s["length"] = s["length"] or 240
        s["sections"] = s["sections"] or 3
        s["segments_per_section"] = s["segments_per_section"] or max(1, round(s["length"] / 11) // s["sections"])
    return suggestions


def generate_topic(custom_prompt: str) -> dict | None:
    """Generate a single topic suggestion using the provided prompt."""
    messages = [
        {"role": "system", "content": load_system_prompt(custom_prompt)},
        {"role": "user", "content": "Generate one short-form video idea."},
    ]
    resp = openai.ChatCompletion.create(
        model=MODEL,
        messages=messages,
        temperature=0.8,
        max_tokens=1000,
    )
    raw = resp["choices"][0]["message"]["content"]
    suggestions = parse_suggestions(raw)
    return suggestions[0] if suggestions else None

# Heuristic scoring
def score_feasibility(title: str) -> tuple[int, str]:
    t = title.lower()
    hard = ["war", "rescue", "earthquake", "plane crash", "natural disaster", "live footage"]
    easy = ["tips", "hacks", "facts", "list", "revealed", "exposed", "tech", "gadgets", "products"]
    if any(k in t for k in hard):
        return 2, "Challenging – may need real-world footage."
    if any(k in t for k in easy):
        return 5, "Simple – AI/stock visuals should suffice."
    return 4, "Moderate – manageable with creative AI & stock assets."

# MAIN: Generate & save topic with retry loop
def generate_daily_video_idea(system_prompt: str | None = None) -> None:
    history = load_history()
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    used_today = [h["title"] for h in history if h["date"] == today_str]

    base_prompt = (
        f"Avoid these titles: {', '.join(used_today) if used_today else 'None'}. "
        "Generate five fresh short-form video ideas."
    )
    messages = [
        {"role": "system", "content": load_system_prompt(system_prompt)},
        {"role": "user", "content": base_prompt},
    ]
    max_attempts = 3
    for attempt in range(max_attempts):
        resp = openai.ChatCompletion.create(
            model=MODEL,
            messages=messages,
            temperature=0.8,
            max_tokens=1500,
        )
        raw = resp["choices"][0]["message"]["content"]
        print("--- RAW GPT OUTPUT ---\n" + raw)
        suggestions = parse_suggestions(raw)
        # Filter unique
        unique = []
        for sug in suggestions:
            if not any(titles_too_similar(sug["title"], u["title"]) for u in unique):
                unique.append(sug)
        # Exclude already used today
        unique = [s for s in unique if s["title"] not in used_today]
        if unique:
            break
        logging.warning(f"No unique suggestions found (attempt {attempt+1}/{max_attempts}). Retrying with stricter guidance...")
        messages.append({
            "role": "user",
            "content": "Ensure all titles are entirely new and do not resemble any previously used concepts."
        })
    else:
        print("❌ No valid unique suggestions were returned after multiple attempts.")
        return

    # Score & pick best
    for s in unique:
        score, reason = score_feasibility(s["title"])
        s.update({"score": score, "reason": reason})
    unique.sort(key=lambda d: -d["score"])
    best = unique[0]

    # Save plan
    slug = re.sub(r"[^a-z0-9]+", "_", best["title"].lower()).strip("_")
    plan_file = f"video_plan_{today_str}_{slug}.json"
    plan = {
        "title": best["title"],
        "subject": best.get("subject", ""),
        "extra_info": best.get("extrainfo", ""),
        "generated_titles": [s["title"] for s in unique],
        "feasibility": {"score": best["score"], "details": best["reason"]},
        "structure": {
            "length": best["length"],
            "sections": best["sections"],
            "segments_per_section": best["segments_per_section"]
        },
        "resolution": "1920x1080",
        "hashtags": best.get("hashtags", ""),
        "description": best.get("description", ""),
    }
    with open(plan_file, "w") as f:
        json.dump(plan, f, indent=4)

    # Update history and save
    history.append({"date": today_str, "title": best["title"]})
    save_history(history)

    print(f"✅ Saved plan to {plan_file}")
    print(f"Subject → {best.get('subject', '')}")
    print(f"Title   → {best['title']} (score {best['score']})")

if __name__ == "__main__":
    generate_daily_video_idea()
