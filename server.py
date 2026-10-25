import os

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000

PROVIDER = os.getenv("PROVIDER", "gemini").lower()
API_KEY = os.getenv("API_KEY", "")
MODEL = os.getenv("MODEL") or {
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
}.get(PROVIDER, "")

MAX_OUTPUT_TOKENS = 512
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": "CampusMateAI/1.0"})


def load_facts():
    try:
        with open("knowledge.md", encoding="utf-8") as facts_file:
            return facts_file.read()
    except FileNotFoundError:
        return ""


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
    messages = [
        {"role": item["role"], "content": item["content"][:4000]}
        for item in history
        if isinstance(item, dict)
        and item.get("role") in ("user", "assistant")
        and isinstance(item.get("content"), str)
        and item["content"]
    ][-8:]
    messages.append({"role": "user", "content": message})

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


@app.after_request
def apply_cache_control(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    else:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
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
    if not API_KEY:
        return jsonify(
            error="No API key set. Add API_KEY to your .env file and restart the server."
        ), 500

    history = data.get("history")
    if not isinstance(history, list):
        history = []

    try:
        return jsonify(answer=call_model(history, message))
    except UpstreamError as error:
        return jsonify(error=error.user_message), error.status
    except requests.RequestException:
        return jsonify(
            error="Could not reach the AI provider. Check your internet connection."
        ), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))