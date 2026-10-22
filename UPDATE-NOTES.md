# IRAS update

## Put it live
1. Unzip into your IRAS folder. Run `git status` and check that `.env` is not in the list.
2. `git add clients src tests UPDATE-NOTES.md`, then `git commit -m "Update"`, then `git push`.
3. After Render finishes the deploy, open the site and press Ctrl+F5.

## Her new voice (Gemini)
- In Render, Environment: check `GEMINI_API_KEY` is set (the key her chat brain uses).
- Optional: `IRAS_TTS_ENGINE` = `gemini` (every screen, the old page too, uses it). `IRAS_GEMINI_VOICE` = `Leda` (try `Aoede`, `Sulafat`, `Zephyr`, `Despina`).
- New screen: Settings, then Voice, pick "Human · Gemini Leda", press "Test her voice".
- If Gemini fails, she uses the old voice and the test message says why.

## Reminders
- Agents screen, Routines, press "Remind me". Type what, then when: "in 10 minutes", "at 5pm", "tomorrow at 9".
- At that time she shows a notice and says it out loud. The page must be open. It checks every 20 seconds.
- Needs the server files in this zip (`src/iras/v5/reminders.py` and `runtime.py`).

## Long answers
She reads the first few sentences aloud, then says the rest is on screen.

## Tests
`python -m pytest tests/test_gemini_tts.py tests/test_reminders.py`
