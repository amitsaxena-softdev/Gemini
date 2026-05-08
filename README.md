# Gemini Voice Chat

Gemini Voice Chat is a small Python app that listens through your microphone, sends the conversation to the Gemini API, and speaks responses back (macOS voice output is supported).

## Features
- Live speech-to-text via Google Speech Recognition
- Conversational responses from the Gemini API
- Optional spoken playback on macOS

## Prerequisites
- Python 3.9+
- A working microphone
- PortAudio system library (required for PyAudio)

## Setup
1. Install PortAudio (system dependency for PyAudio):
   - macOS: `brew install portaudio`
   - Ubuntu/Debian: `sudo apt-get install portaudio19-dev`
2. Create and activate a virtual environment.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure your API key (either works):
   ```bash
   cp .env.example .env
   ```
   Set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) in `.env`.

## Usage
Run the app:
```bash
python main.py
```

Say “exit”, “quit”, or “stop” to end the session.

## Configuration
Optional environment variables:
- `GEMINI_MODEL` (default: `gemini-2.0-flash`)
- `MAX_HISTORY_TURNS` (default: `10`)
- `MAX_GENERATION_RETRIES` (default: `2`)
- `MAX_STT_RETRIES` (default: `3`)
- `RETRY_BACKOFF_SECONDS` (default: `1.5`)
- `MAX_RETRY_BACKOFF_SECONDS` (default: `10.0`)
- `LOG_LEVEL` (default: `INFO`)

## Notes
- Voice playback uses the macOS `say` command. On other platforms, responses are printed to the console.
