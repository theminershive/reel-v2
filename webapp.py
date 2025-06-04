import threading
import uuid
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

from voices_and_styles import VOICES, MODELS
from config import VIDEO_SCRIPTS_DIR
from web_pipeline import run_pipeline

app = Flask(__name__)

jobs = {}


def worker(job_id, topic, length, voice, style, num_sections, num_segments, prompt_template, topic_prompt):
    try:
        video = run_pipeline(
            topic,
            int(length),
            voice,
            style,
            num_sections=num_sections,
            num_segments=num_segments,
            prompt_template=prompt_template,
            topic_prompt=topic_prompt,
        )
        jobs[job_id] = {"status": "done", "video": video}
    except Exception as e:
        jobs[job_id] = {"status": "error", "message": str(e)}


@app.route("/")
def index():
    return render_template("index.html", voices=VOICES.keys(), styles=MODELS.keys())


@app.route("/start", methods=["POST"])
def start():
    topic = request.form.get("topic", "")
    length = request.form.get("length", 60)
    voice = request.form.get("voice")
    style = request.form.get("style")
    num_sections = int(request.form.get("num_sections", 3))
    num_segments = int(request.form.get("num_segments", 3))
    prompt_template = request.form.get("prompt_template") or None
    topic_prompt = request.form.get("topic_prompt") or None
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running"}
    t = threading.Thread(
        target=worker,
        args=(job_id, topic, length, voice, style, num_sections, num_segments, prompt_template, topic_prompt),
    )
    t.start()
    return render_template("status.html", job_id=job_id)


@app.route("/status/<job_id>")
def status(job_id):
    return jsonify(jobs.get(job_id, {"status": "unknown"}))


@app.route("/video/<job_id>")
def video(job_id):
    job = jobs.get(job_id)
    if job and job.get("status") == "done":
        return send_file(job["video"], as_attachment=True)
    return "Not ready", 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
