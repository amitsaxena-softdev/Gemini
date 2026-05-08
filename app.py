import logging
import os
import platform
import subprocess
import time

from dotenv import load_dotenv
from google import genai
import speech_recognition as sr

load_dotenv()

EXIT_COMMANDS = {"exit", "quit", "stop", "goodbye"}
DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_MAX_HISTORY_TURNS = 10
DEFAULT_MAX_GENERATION_RETRIES = 2
DEFAULT_MAX_STT_RETRIES = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 1.5
DEFAULT_MAX_RETRY_BACKOFF_SECONDS = 10.0
RETRYABLE_EXCEPTION_MODULE_PREFIXES = ("google", "grpc", "httpx", "requests")
RETRYABLE_EXCEPTIONS = (OSError, TimeoutError, ConnectionError)

logger = logging.getLogger(__name__)


def configure_logging():
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s:%(name)s:%(message)s")


def get_env_int(name, default, minimum=None, maximum=None):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("%s must be an integer. Using %s.", name, default)
        return default
    if minimum is not None and value < minimum:
        logger.warning("%s must be >= %s. Using %s.", name, minimum, default)
        return default
    if maximum is not None and value > maximum:
        logger.warning("%s must be <= %s. Using %s.", name, maximum, default)
        return default
    return value


def get_env_float(name, default, minimum=None, maximum=None):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning("%s must be a number. Using %s.", name, default)
        return default
    if minimum is not None and value < minimum:
        logger.warning("%s must be >= %s. Using %s.", name, minimum, default)
        return default
    if maximum is not None and value > maximum:
        logger.warning("%s must be <= %s. Using %s.", name, maximum, default)
        return default
    return value


def is_retryable_exception(exc):
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True
    module_name = exc.__class__.__module__
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in RETRYABLE_EXCEPTION_MODULE_PREFIXES
    )


def speak_text(text, voice_state):
    if not text.strip():
        return

    if platform.system() == "Darwin":
        try:
            subprocess.run(["say", text], check=True)
        except FileNotFoundError as exc:
            logger.warning("macOS say command not found: %s", exc)
        except (OSError, subprocess.CalledProcessError) as exc:
            logger.warning("AI voice playback failed: %s", exc)
    else:
        if not voice_state.get("warned"):
            print("AI voice playback is only configured for macOS right now.")
            voice_state["warned"] = True


def listen_and_transcribe(recognizer, max_retries, retry_backoff):
    attempts = 0
    while True:
        try:
            with sr.Microphone() as source:
                print("\nListening... Speak now!")
                try:
                    audio = recognizer.listen(source, timeout=10, phrase_time_limit=20)
                except sr.WaitTimeoutError:
                    print("I didn't hear anything. Let's try again.")
                    continue
        except OSError as exc:
            logger.error("Microphone error: %s", exc)
            return None

        try:
            print("Processing your speech...")
            user_speech = recognizer.recognize_google(audio).strip()
            if not user_speech:
                print("I heard silence. Please try again.")
                continue

            print(f"You said: {user_speech}")
            return user_speech
        except sr.UnknownValueError:
            print("Sorry, I couldn't understand that. Please try again.")
        except sr.RequestError as exc:
            attempts += 1
            logger.warning("Speech recognition is unavailable right now: %s", exc)
            if attempts > max_retries:
                logger.error("Speech recognition failed after %s attempts.", attempts)
                return None
            print("Speech recognition is temporarily unavailable. Retrying...")
            time.sleep(retry_backoff)


def build_prompt(history, latest_user_input):
    transcript = "\n".join(history)
    return (
        "You are in a live spoken conversation with a user. "
        "Reply naturally, keep answers concise unless asked for detail, "
        "and avoid markdown.\n\n"
        f"Conversation so far:\n{transcript}\n"
        f"User: {latest_user_input}\n"
        "Assistant:"
    )


def trim_history(history, max_turns):
    if max_turns <= 0:
        return []
    max_entries = max_turns * 2
    if len(history) <= max_entries:
        return history
    return history[-max_entries:]


def generate_response(client, model, prompt, max_retries, retry_backoff, max_backoff):
    attempts = 0
    while True:
        should_retry = False
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            text = (response.text or "").strip()
            if text:
                return text
            logger.warning("Gemini returned an empty response.")
            should_retry = True
        except Exception as exc:
            if not is_retryable_exception(exc):
                raise
            logger.warning("Gemini request failed: %s", exc)
            should_retry = True

        if not should_retry:
            return None
        attempts += 1
        if attempts > max_retries:
            return None
        sleep_seconds = retry_backoff * (2 ** (attempts - 1))
        if max_backoff > 0:
            sleep_seconds = min(sleep_seconds, max_backoff)
        time.sleep(sleep_seconds)


def app():
    configure_logging()
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.8
    recognizer.non_speaking_duration = 0.5

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY or GOOGLE_API_KEY in your environment.")

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    max_history_turns = get_env_int("MAX_HISTORY_TURNS", DEFAULT_MAX_HISTORY_TURNS, minimum=0)
    max_generation_retries = get_env_int(
        "MAX_GENERATION_RETRIES", DEFAULT_MAX_GENERATION_RETRIES, minimum=0
    )
    max_stt_retries = get_env_int("MAX_STT_RETRIES", DEFAULT_MAX_STT_RETRIES, minimum=0)
    retry_backoff = get_env_float(
        "RETRY_BACKOFF_SECONDS", DEFAULT_RETRY_BACKOFF_SECONDS, minimum=0
    )
    max_retry_backoff = get_env_float(
        "MAX_RETRY_BACKOFF_SECONDS", DEFAULT_MAX_RETRY_BACKOFF_SECONDS, minimum=0
    )

    try:
        with sr.Microphone() as source:
            print("Adjusting for background noise... one second.")
            recognizer.adjust_for_ambient_noise(source, duration=1)
    except OSError as exc:
        logger.error("Microphone error during setup: %s", exc)
        return

    print("Voice chat is ready. Say 'exit', 'quit', or 'stop' to end the session.")
    conversation_history = []
    voice_state = {"warned": False}

    while True:
        user_input = listen_and_transcribe(recognizer, max_stt_retries, retry_backoff)
        if user_input is None:
            break

        if user_input.lower() in EXIT_COMMANDS:
            print("Ending voice chat.")
            break

        prompt = build_prompt(conversation_history, user_input)
        ai_text = generate_response(
            client,
            model,
            prompt,
            max_generation_retries,
            retry_backoff,
            max_retry_backoff,
        )
        if not ai_text:
            ai_text = "I couldn't generate a response just now. Please try again."

        print(f"AI: {ai_text}")
        speak_text(ai_text, voice_state)

        conversation_history.append(f"User: {user_input}")
        conversation_history.append(f"Assistant: {ai_text}")
        conversation_history = trim_history(conversation_history, max_history_turns)


if __name__ == "__main__":
    app()
