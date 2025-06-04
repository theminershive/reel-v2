# reel-v2

`reel-v2` is a collection of utilities that generate short form videos using several AI services.  It can create a script with GPT, generate images, synthesize speech, assemble the final video and optionally upload it to various social networks.

## Features

- **Script generation** via OpenAI ChatGPT
- **Image generation** using a local Flux or Leonardo API
- **Text to speech** with a local TTS server
- **Automatic captioning** with Whisper
- **Video assembly** with MoviePy and Freesound assets
- **Upload helpers** for YouTube, Facebook and Instagram
- Simple FastAPI servers for Flux image generation and Coqui‑TTS

## Installation

1. Install Python 3.10 or newer.
2. Install the Python dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root containing your API keys.  At a minimum you should define:

```
OPENAI_API_KEY=<your key>
FREESOUND_API_KEY=<your key>
LEONARDO_API_KEY=<your key>
USER_ACCESS_TOKEN=<facebook token>
FACEBOOK_PAGE_ID=<page id>
INSTAGRAM_ACCOUNT_ID=<account id>
SMTP_SERVER=<smtp host>
SMTP_USER=<smtp user>
SMTP_PASSWORD=<smtp password>
EMAIL_RECIPIENT=<your email>
```

The `config` module now loads this file automatically, so simply importing
`config` ensures all environment variables are available throughout the
project.

Additional variables such as `WHISPER_API_URL` or `LOCAL_TTS_URL` can be used to point to your local services.  See the code for the full list.

## Usage

Generate a daily video idea:

```bash
python topic.py
```

Run the full workflow using the latest plan:

```bash
python auto.py
```

You can also call `app.py --plan <plan.json>` directly with a custom plan file.

The repository includes optional servers:

- `serverflux.py` – FastAPI wrapper around the Flux image generation pipeline
- `servertts.py` – Coqui‑TTS server with a simple HTTP API

## Development notes


## License

MIT
