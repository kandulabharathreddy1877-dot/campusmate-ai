import os
import requests
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import time

load_dotenv()
app = Flask(__name__, static_folder="static", static_url_path="")

PROVIDER = os.getenv("PROVIDER", "gemini").lower()   # gemini | anthropic | openai
API_KEY = os.getenv("API_KEY", "")
MODEL = os.getenv("MODEL") or {
    "gemini": "gemini-3.8-flash",
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",

}def post_retry(*args, **kwargs):
    for attempt in range(3):
        r = requests.post(*args, **kwargs)
        if r.status_code not in (429, 503):
            return r
        time.sleep(2 * (attempt + 1))
    return r
[PROVIDER]

def load_facts():
    try:
        with open("knowledge.md", encoding="utf-8") as f:
            return f.read()
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
        self.user_message, self.status = user_message, status

def call_model(history, message):
    msgs = [{"role": m["role"], "content": m["content"]} for m in history
            if m.get("role") in ("user", "assistant") and m.get("content")]
    msgs.append({"role": "user", "content": message})

    if PROVIDER == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
        contents = [{"role": "model" if m["role"] == "assistant" else "user",
                     "parts": [{"text": m["content"]}]} for m in msgs]
        contents[0]["parts"][0]["text"] = SYSTEM + "\n\nStudent question:\n" + contents[0]["parts"][0]["text"]
        body = {"contents": contents}
                r = post_retry(url, json=body, headers={"x-goog-api-key": API_KEY}, timeout=60)
        pick = lambda j: j["candidates"][0]["content"]["parts"][0]["text"]
    elif PROVIDER == "anthropic":
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=60,
            headers={"x-api-key": API_KEY, "anthropic-version": "2023-06-01"},
            json={"model": MODEL, "max_tokens": 800, "system": SYSTEM, "messages": msgs})
        pick = lambda j: j["content"][0]["text"]
    elif PROVIDER == "openai":
        r = requests.post("https://api.openai.com/v1/chat/completions", timeout=60,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}] + msgs})
        pick = lambda j: j["choices"][0]["message"]["content"]
    else:
        raise UpstreamError("Server setup error: PROVIDER must be gemini, anthropic or openai.", 500)

    if r.status_code in (401, 403):
        raise UpstreamError("The API key was rejected. Check API_KEY in your .env file.")
    if r.status_code == 503:
        raise UpstreamError("The AI is busy right now. Please try again in a minute.")
    if r.status_code == 429:
        raise UpstreamError("The AI provider says quota or credits are used up. Add billing or wait, then retry.")
    if not r.ok:
        print("Provider error:", r.status_code, r.text[:500])
        raise UpstreamError("The AI service returned an error. Check the server console for details.")
    try:
        return pick(r.json()).strip()
    except (KeyError, IndexError):
        raise UpstreamError("The AI service sent an empty reply. Try rephrasing your question.")

@app.get("/")
def index():
    return send_from_directory("static", "index.html")

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify(error="Type a question first."), 400
    if len(message) > 2000:
        return jsonify(error="That question is too long. Keep it under 2000 characters."), 400
    if not API_KEY:
        return jsonify(error="No API key set. Add API_KEY to your .env file and restart the server."), 500
    try:
        return jsonify(answer=call_model(data.get("history") or [], message))
    except UpstreamError as e:
        return jsonify(error=e.user_message), e.status
    except requests.RequestException:
        return jsonify(error="Could not reach the AI provider. Check your internet connection."), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
