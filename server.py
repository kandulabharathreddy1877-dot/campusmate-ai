import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv, set_key
from flask import (
    Flask,
    Response,
    jsonify,
    request,
    send_from_directory,
    stream_with_context,
)

ENV_FILE = Path(__file__).with_name(".env")
load_dotenv(ENV_FILE)

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

PROVIDER = os.getenv("PROVIDER", "gemini").lower()
API_KEY = os.getenv("API_KEY", "")
MODEL = os.getenv("MODEL") or {
    "gemini": "gemini-3.5-flash-lite",
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
}.get(PROVIDER, "")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
LOCAL_SETTINGS_ENABLED = os.getenv("LOCAL_SETTINGS_ENABLED", "true").lower() == "true"

MAX_OUTPUT_TOKENS = 256
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": "CampusMateAI/1.0"})


def is_local_request():
    return request.remote_addr in ("127.0.0.1", "::1")


def load_facts():
    try:
        with open("knowledge.md", encoding="utf-8") as facts_file:
            return facts_file.read()
    except FileNotFoundError:
        return ""


def build_messages(history, message):
    messages = [
        {"role": item["role"], "content": item["content"][:4000]}
        for item in history
        if isinstance(item, dict)
        and item.get("role") in ("user", "assistant")
        and isinstance(item.get("content"), str)
        and item["content"]
    ][-4:]
    messages.append({"role": "user", "content": message})
    return messages


SYSTEM = """- If someone asks who created you or who built this website, say you were created by Bharath Kumar Reddy.
You are CampusMate AI, an unofficial student assistant for Mohan Babu University (MBU), Tirupati, India.
Help with questions about the university, courses, admissions, fees, scholarships, placements, hostel and campus life.
Rules:
- Use the VERIFIED FACTS below first. If something is not covered there and you are not sure, say you don't have verified details.
- Never invent fees, dates, cut-offs, placement numbers or company names.
- For anything official (fees, deadlines, eligibility), point to https://admissions.mbu.asia/ or the MBU website.
- Be concise and friendly. Use short paragraphs or simple '-' bullet lists. Do not use headings or tables.

VERIFIED FACTS:
""" + load_facts()


class UpstreamError(Exception):
    def __init__(self, user_message, status=502):
        super().__init__(user_message)
        self.user_message = user_message
        self.status = status


def call_model(history, message):
    messages = build_messages(history, message)

    timeout = (5, 45)

    if PROVIDER == "gemini":
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{MODEL}:generateContent"
        )
        contents = [
            {
                "role": "model" if item["role"] == "assistant" else "user",
                "parts": [{"text": item["content"]}],
            }
            for item in messages
        ]
        response = HTTP.post(
            url,
            headers={"x-goog-api-key": API_KEY},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM}]},
                "contents": contents,
                "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
            },
            timeout=timeout,
        )
        extract_answer = lambda data: data["candidates"][0]["content"]["parts"][0]["text"]

    elif PROVIDER == "anthropic":
        response = HTTP.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": MODEL,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "system": SYSTEM,
                "messages": messages,
            },
            timeout=timeout,
        )
        extract_answer = lambda data: data["content"][0]["text"]

    elif PROVIDER == "openai":
        response = HTTP.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "messages": [{"role": "system", "content": SYSTEM}] + messages,
            },
            timeout=timeout,
        )
        extract_answer = lambda data: data["choices"][0]["message"]["content"]

    else:
        raise UpstreamError(
            "Server setup error: PROVIDER must be gemini, anthropic or openai.",
            500,
        )

    if response.status_code in (401, 403):
        raise UpstreamError("The API key was rejected. Check API_KEY in your .env file.")
    if response.status_code == 503:
        raise UpstreamError("The AI is busy right now. Please try again in a minute.")
    if response.status_code == 429:
        raise UpstreamError(
            "The AI provider says quota or credits are used up. Add billing or wait, then retry."
        )
    if not response.ok:
        print("Provider error:", response.status_code, response.text[:500])
        raise UpstreamError(
            "The AI service returned an error. Check the server console for details."
        )

    try:
        answer = extract_answer(response.json()).strip()
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise UpstreamError(
            "The AI service sent an empty reply. Try rephrasing your question."
        ) from error

    if not answer:
        raise UpstreamError(
            "The AI service sent an empty reply. Try rephrasing your question."
        )
    return answer


def open_gemini_stream(history, message):
    contents = [
        {
            "role": "model" if item["role"] == "assistant" else "user",
            "parts": [{"text": item["content"]}],
        }
        for item in build_messages(history, message)
    ]
    models = [MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL not in models:
        models.append(GEMINI_FALLBACK_MODEL)

    for index, model in enumerate(models):
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:streamGenerateContent?alt=sse"
        )
        response = HTTP.post(
            url,
            headers={"x-goog-api-key": API_KEY},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM}]},
                "contents": contents,
                "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
            },
            timeout=(5, 45),
            stream=True,
        )
        if response.status_code == 503 and index + 1 < len(models):
            print(f"Gemini model {model} returned 503; trying fallback model {models[index + 1]}.")
            response.close()
            continue
        if response.status_code in (401, 403):
            response.close()
            raise UpstreamError("The API key was rejected. Check API_KEY in your .env file.")
        if response.status_code == 503:
            response.close()
            raise UpstreamError(
                "Gemini is unavailable on both the primary and fallback models right now. "
                "Check https://aistudio.google.com/status and verify your API key and quota."
            )
        if response.status_code == 429:
            response.close()
            raise UpstreamError(
                "The Gemini API quota or rate limit was reached. Check your Google AI Studio limits."
            )
        if not response.ok:
            print("Provider error:", response.status_code, response.text[:500])
            response.close()
            raise UpstreamError(
                "The AI service returned an error. Check the server console for details."
            )
        return response

    raise UpstreamError("No Gemini model is configured.", 500)


def encode_stream_event(data):
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_gemini_response(response):
    answer_received = False
    try:
        for raw_line in response.iter_lines(chunk_size=1):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if not line.startswith("data:"):
                continue
            try:
                data = json.loads(line[5:].strip())
                parts = data["candidates"][0]["content"]["parts"]
            except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
                raise UpstreamError(
                    "The AI service sent an invalid reply. Please try again."
                ) from error
            for part in parts:
                text = part.get("text")
                if isinstance(text, str) and text:
                    answer_received = True
                    yield encode_stream_event({"text": text})
        if not answer_received:
            yield encode_stream_event(
                {"error": "The AI service sent an empty reply. Try rephrasing your question."}
            )
    except UpstreamError as error:
        yield encode_stream_event({"error": error.user_message})
    except requests.RequestException:
        yield encode_stream_event(
            {"error": "Could not reach the AI provider. Check your internet connection."}
        )
    finally:
        response.close()


@app.after_request
def apply_cache_control(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    else:
        response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify(error="Type a question first."), 400

    message = message.strip()
    if len(message) > 2000:
        return jsonify(error="That question is too long. Keep it under 2000 characters."), 400
    if not API_KEY.strip() or API_KEY.strip().lower() == "your_api_key_here":
        return jsonify(
            error="No valid API key is configured. Set API_KEY in the server environment and restart the service."
        ), 500

    history = data.get("history")
    if not isinstance(history, list):
        history = []

    if PROVIDER == "gemini":
        try:
            upstream_response = open_gemini_stream(history, message)
        except UpstreamError as error:
            return jsonify(error=error.user_message), error.status
        except requests.RequestException:
            return jsonify(
                error="Could not reach the AI provider. Check your internet connection."
            ), 502
        return Response(
            stream_with_context(stream_gemini_response(upstream_response)),
            mimetype="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )

    try:
        return jsonify(answer=call_model(history, message))
    except UpstreamError as error:
        return jsonify(error=error.user_message), error.status
    except requests.RequestException:
        return jsonify(
            error="Could not reach the AI provider. Check your internet connection."
        ), 502


@app.get("/api/settings")
def get_settings():
    if not LOCAL_SETTINGS_ENABLED or not is_local_request():
        return jsonify(error="Settings are only available on this computer."), 403
    return jsonify(api_key_configured=bool(API_KEY.strip()))


@app.post("/api/settings")
def save_settings():
    if not LOCAL_SETTINGS_ENABLED or not is_local_request():
        return jsonify(error="Settings are only available on this computer."), 403

    data = request.get_json(silent=True)
    api_key = data.get("api_key") if isinstance(data, dict) else None
    if not isinstance(api_key, str) or not api_key.strip():
        return jsonify(error="Enter your Gemini API key."), 400

    api_key = api_key.strip()
    if len(api_key) > 512:
        return jsonify(error="The API key is too long."), 400

    try:
        saved, _, _ = set_key(str(ENV_FILE), "API_KEY", api_key, quote_mode="always")
    except OSError:
        return jsonify(error="Could not save .env. Check that the project folder is writable."), 500
    if not saved:
        return jsonify(error="Could not save .env. Check that the project folder is writable."), 500

    global API_KEY
    API_KEY = api_key
    return jsonify(saved=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))