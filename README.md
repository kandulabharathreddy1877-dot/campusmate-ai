# CampusMate AI

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, set `PROVIDER` and `API_KEY`.
   - Free option: get a Gemini key at https://aistudio.google.com/apikey and use PROVIDER=gemini
   - Gemini uses `gemini-3.5-flash-lite` for fast streamed replies and automatically tries `gemini-2.5-flash` if the primary model is temporarily unavailable. Set `MODEL` and `GEMINI_FALLBACK_MODEL` in `.env` to change them.
3. Edit `knowledge.md` with verified MBU facts.
4. `python server.py`, then open http://127.0.0.1:5000
