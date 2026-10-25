# CampusMate AI

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, set `PROVIDER` and `API_KEY`.
   - Free option: get a Gemini key at https://aistudio.google.com/apikey and use PROVIDER=gemini
   - For faster Gemini responses, use `MODEL=gemini-3.5-flash-lite`; Gemini replies stream into the chat as they are generated.
3. Edit `knowledge.md` with verified MBU facts.
4. `python server.py`, then open http://127.0.0.1:5000
