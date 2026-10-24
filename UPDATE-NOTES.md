# IRAS update

## Put it live
1. Unzip into your IRAS folder. Run `git status` and check that `.env` is not in the list.
2. `git add clients src tests pyproject.toml Dockerfile UPDATE-NOTES.md`, then `git commit -m "Update"`, then `git push`.
3. Render rebuilds (the first build is longer, it installs the Face ID and calendar packages). Then open the site and press Ctrl+F5.
4. This push does not start the Android or Windows builds, because nothing in them changed. The phone and PC apps show the same screen, so they get the new Voice ID card as soon as Render is live.

## Calendar (new)
- Google Calendar: Settings, your calendar, "Integrate calendar", copy "Secret address in iCal format". Any private .ics link works (Outlook, Apple, Nextcloud).
- New screen: Agents, Calendar, Add, paste the link. She lists your next events and reminds you 10 minutes before each one, out loud (the page must be open). Every 15 minutes she checks for new, moved or removed events.
- The link is a secret: anyone with it can read your calendar. It is kept in your database and never sent back to the screen. To keep it encrypted, set `IRAS_VAULT_MASTER_KEY` in Render. Make a key with: `python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`. If the link leaks, reset the secret address in Google Calendar.
- She says the clock time only when the calendar tells its time zone (Google does). All-day events are listed but get no reminder.
- If your Render plan sleeps when idle, reminders can be late.

## Face ID
- Identity, "Start camera", write your name, "Teach her my face" (5 pictures, turn your head a little). Then "Who is this?".
- Only 512 numbers per picture are saved. No photo is kept. The bin button forgets the face (the voice stays).
- The first picture downloads two small face models (15 MB) from GitHub. They are free for personal and research use, not for selling.
- A match needs 0.45 and must beat the next person by 0.05 (`IRAS_FACE_THRESHOLD`). The head-turn check is basic. Face ID never replaces an approval.
- Render's free plan has 512 MB of memory. If the server restarts when you use Face ID, tell me.

## Voice ID (new)
- Identity, Voice ID card: write your name, press "Teach her my voice". She shows 3 lines. Read each one out loud (8 seconds each), or just talk, in any language. Then "Who is speaking?" listens for 6 seconds. The bin button forgets the voice (the face stays).
- Only 256 numbers per recording are saved. No recording is kept: the sound goes to your server for one check and is thrown away.
- The first recording downloads one small voice model (26 MB) from GitHub: WeSpeaker ResNet34. The download is checked against a fixed checksum. WeSpeaker says its VoxCeleb models are CC BY 4.0, so give credit to WeSpeaker if you share this. It is loaded for each check and let go after, to save memory.
- A match needs 0.50 and must beat the next person by 0.06 (`IRAS_VOICE_THRESHOLD`). A teaching recording that sounds very different from the voice she already knows is refused (`IRAS_VOICE_SAME`, 0.30). Optional: `IRAS_VOICE_KEEP_LOADED=1` keeps the model in memory.
- A voice can be recorded and played back. Voice ID only helps her know who is talking. It never replaces an approval.
- The microphone is on only while a recording runs, only on this screen, and the header "Mic" chip shows it. Leaving the screen stops it.
- My test: real voices of 5 people. The same person scored 0.73 to 0.77, different people 0.35 at most. That is a small test, with clean sound. Your own microphone may score lower. If she often says "not sure" when it is you, tell me the percent she shows.
- Render's free plan has 512 MB of memory. The voice model needs about 70 to 130 MB while it runs. If the server restarts when you use Voice ID, tell me.

## Old demo files
- `clients/web/command-center/src/js/25-data.js` and `30-sim.js` are the old demo. The page does not use them. `build.py` now skips them, so a rebuild cannot bring the demo back. You can delete them later (one old test, `test_command_center_ui.py`, still reads `30-sim.js`).
- `clients/web/index.html` is the page the server shows. It is already rebuilt. To rebuild it after you change the sources: `python clients/web/command-center/build.py --check`.

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
`python -m pytest tests/test_gemini_tts.py tests/test_reminders.py tests/test_identity.py tests/test_voice.py tests/test_agenda.py`
(`test_voice.py` runs the real voice model only if the model file is already on your computer. It never downloads anything.)
