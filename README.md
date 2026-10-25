# CampusMate AI

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, set `PROVIDER` and `API_KEY`.
   - Free option: get a Gemini key at https://aistudio.google.com/apikey and use PROVIDER=gemini
   - Gemini uses `gemini-3.5-flash-lite` for fast streamed replies and automatically tries `gemini-2.5-flash` if the primary model is temporarily unavailable. Set `MODEL` and `GEMINI_FALLBACK_MODEL` in `.env` to change them.
3. Edit `knowledge.md` with verified MBU facts.
4. `python server.py`, then open http://127.0.0.1:5000

You can also open **API settings** on the local website to save or replace the Gemini key in your local `.env` file. The settings endpoint only accepts requests from this computer, and the website never displays the saved key. Keep `.env` private and do not commit it.

## Deploying publicly on Render

1. Push the project source to a GitHub repository and connect that repository to Render. Never add `.env` or an API key to GitHub.
2. In Render, choose **New +** → **Blueprint** and select the repository containing `render.yaml`.
3. Enter your Gemini API key in Render's private `API_KEY` environment-variable prompt, then create the web service. Do not put the key in source code or `render.yaml`.
4. After deployment completes, open the `onrender.com` URL shown in the Render dashboard. Anyone with that URL can use the chat; usage consumes your Gemini quota and may incur provider charges.

`render.yaml` configures the service to start with Gunicorn and disables the local API-key settings page on the public deployment. Replace the exposed Gemini key with a newly generated key before deploying.
