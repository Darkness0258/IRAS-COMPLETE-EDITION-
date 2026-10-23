# IRAS update

## Put it live
1. Unzip into your IRAS folder. Run `git status` and check that `.env` is not in the list.
2. `git add clients src tests pyproject.toml Dockerfile UPDATE-NOTES.md`, then `git commit -m "Update"`, then `git push`.
3. Render rebuilds (the first build is longer, see Face ID). Then open the site and press Ctrl+F5.

## Face ID (new)
- Open Identity, press "Start camera", write your name, press "Teach her my face". Follow the 5 steps (turn your head a little each time). Then try "Who is this?".
- Only 512 numbers per picture are saved in your database. No photo is kept. The bin button forgets a person.
- Render installs 3 extra packages (numpy, onnxruntime, opencv). The first picture downloads two small face models (15 MB) from GitHub. These models are free for personal and research use, not for selling.
- Tested here on real photos: different people scored about 0.0, the same person 0.6 to 0.98. A match needs 0.45 and must beat the next person by 0.05. `IRAS_FACE_THRESHOLD` changes it.
- The head-turn check is basic: it can tell a still photo from a person turning, but a video can fool it. Face ID tells her who is there. It never replaces an approval.
- Render's free plan has 512 MB of memory. If the server restarts when you use Face ID, tell me.

## Phone and PC
- Phone (Chrome): open the site, menu, "Install app". PC (Edge or Chrome): the install icon in the address bar.
- Android app: the push starts "Build Android APK" on GitHub (Actions). Download `IRAS-Android-APK`. If the phone says "App not installed", uninstall the old IRAS first. The app now shows the same screen as the website, with the phone's own speech recognizer and camera. The old native screen is inside as "Classic" (on the "Cannot reach IRAS" page).
- Windows app: the push starts "Build Windows EXE". New button "Command Center" opens the new screen in its own window and signs you in with the saved token.

## Her new voice (Gemini)
- In Render, Environment: check `GEMINI_API_KEY` is set. Optional: `IRAS_TTS_ENGINE` = `gemini` and `IRAS_GEMINI_VOICE` = `Leda` (try `Aoede`, `Sulafat`, `Zephyr`, `Despina`).
- New screen: Settings, Voice, pick "Human · Gemini Leda", press "Test her voice".

## Reminders
- Agents, Routines, "Remind me": "in 10 minutes", "at 5pm", "tomorrow at 9". She shows a notice and says it out loud (page open, checks every 20 seconds).

## Tests
`python -m pytest tests/test_gemini_tts.py tests/test_reminders.py tests/test_identity.py`
