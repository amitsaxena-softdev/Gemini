import os
import platform
import subprocess

from dotenv import load_dotenv
from google import genai
import speech_recognition as sr

load_dotenv()

EXIT_COMMANDS = {"exit", "quit", "stop", "goodbye"}
DEFAULT_MODEL = "gemini-2.0-flash"


def speak_text(text):
    if not text.strip():
        return

    if platform.system() == "Darwin":
        try:
            subprocess.run(["say", text], check=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            print(f"AI voice playback failed: {exc}")
    else:
        print("AI voice playback is only configured for macOS right now.")


def listen_and_transcribe(recognizer):
    while True:
        with sr.Microphone() as source:
            print("\nListening... Speak now!")
            try:
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=20)
            except sr.WaitTimeoutError:
                print("I didn't hear anything. Let's try again.")
                continue

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
            print(f"Speech recognition is unavailable right now: {exc}")
            return None


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


def app():
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.8
    recognizer.non_speaking_duration = 0.5

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY or GOOGLE_API_KEY in your environment.")

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

    with sr.Microphone() as source:
        print("Adjusting for background noise... one second.")
        recognizer.adjust_for_ambient_noise(source, duration=1)

    print("Voice chat is ready. Say 'exit', 'quit', or 'stop' to end the session.")
    conversation_history = []

    while True:
        user_input = listen_and_transcribe(recognizer)
        if user_input is None:
            break

        if user_input.lower() in EXIT_COMMANDS:
            print("Ending voice chat.")
            break

        prompt = build_prompt(conversation_history, user_input)
        response = client.models.generate_content(model=model, contents=prompt)
        ai_text = (response.text or "").strip()

        if not ai_text:
            ai_text = "I couldn't generate a response just now. Please try again."

        print(f"AI: {ai_text}")
        speak_text(ai_text)

        conversation_history.append(f"User: {user_input}")
        conversation_history.append(f"Assistant: {ai_text}")


if __name__ == "__main__":
    app()
