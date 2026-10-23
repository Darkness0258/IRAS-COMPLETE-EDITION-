# IRAS update

## Put it live
1. Unzip into your IRAS folder. Run `git status` and check that `.env` is not in the list.
2. `git add clients src tests pyproject.toml Dockerfile UPDATE-NOTES.md`, then `git commit -m "Update"`, then `git push`.
3. Render rebuilds (the first build is longer, it installs the Face ID and calendar packages). Then open the site and press Ctrl+F5.

## Calendar (new)
- Google Calendar: Settings, your calendar, "Integrate calendar", copy "Secret address in iCal format". Any private .ics link works (Outlook, Apple, Nextcloud).
- New screen: Agents, Calendar, Add, paste the link. She lists your next events and reminds you 10 minutes before each one, out loud (the page must be open). Every 15 minutes she checks for new, moved or removed events.
- The link is a secret: anyone with it can read your calendar. It is kept in your database and never sent back to the screen. To keep it encrypted, set `IRAS_VAULT_MASTER_KEY` in Render. Make a key with: `python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`. If the link leaks, reset the secret address in Google Calendar.
- She says the clock time only when the calendar tells its time zone (Google does). All-day events are listed but get no reminder.
- If your Render plan sleeps when idle, reminders can be late.

## Face ID
- Identity, "Start camera", write your name, "Teach her my face" (5 pictures, turn your head a little). Then "Who is this?".
- Only 512 numbers per picture are saved. No photo is kept. The bin button forgets a person.
- The first picture downloads two small face models (15 MB) from GitHub. They are free for personal and research use, not for selling.
- A match needs 0.45 and must beat the next person by 0.05 (`IRAS_FACE_THRESHOLD`). The head-turn check is basic. Face ID never replaces an approval.
- Render's free plan has 512 MB of memory. If the server restarts when you use Face ID, tell me.

## Phone and PC
- Phone (Chrome): open the site, menu, "Install app". PC (Edge or Chrome): the install icon in the address bar.
- Android app: the push starts "Build Android APK" on GitHub (Actions). Download `IRAS-Android-APK`. If the phone says "App not installed", uninstall the old IRAS first. The app shows the same screen as the website, with the phone's speech recognizer, camera and pop-up questions. The old native screen is inside as "Classic" (on the "Cannot reach IRAS" page).
- Windows app: the push starts "Build Windows EXE". New button "Command Center" opens the new screen in its own window and signs you in with the saved token.

## Her new voice (Gemini)
- In Render, Environment: check `GEMINI_API_KEY` is set. Optional: `IRAS_TTS_ENGINE` = `gemini` and `IRAS_GEMINI_VOICE` = `Leda` (try `Aoede`, `Sulafat`, `Zephyr`, `Despina`).
- New screen: Settings, Voice, pick "Human · Gemini Leda", press "Test her voice".

## Reminders
- Agents, Routines, "Remind me": "in 10 minutes", "at 5pm", "tomorrow at 9". She shows a notice and says it out loud (page open, checks every 20 seconds).

## Tests
`python -m pytest tests/test_gemini_tts.py tests/test_reminders.py tests/test_identity.py tests/test_agenda.py`
