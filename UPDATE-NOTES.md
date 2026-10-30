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

## Your PC (new)
- New menu item **PC** (also in Ctrl+K). It holds the old page's tools: remote screen, direct action and Master Control. The old page at `/app/classic/` is untouched and still works. A session started on one page is seen by the other, in the same window.
- **Session**: choose what it may do and for how long, then Start. She always asks you first. Look only: see the screen, read files. Control: also open apps, type, click, write files. Full: also run commands, delete, install, power off. While a session is open a badge shows in the top bar, and End session stops it at once.
- **Your server decides the highest level.** By default it allows up to Control. Full sessions and Master need `IRAS_REMOTE_SESSION_MAX_PERMISSION_LEVEL=3` in Render, Environment. Until then Full is greyed out and says why. The old page asked for Full by default, so if its Remote button worked for you, your server already allows it.
- **Screen**: "Show my screen" takes one small picture. "Keep refreshing" takes a new one every 5 seconds while you stay on this screen. It stops when you leave, hide the tab, or after 3 errors.
- **Direct action**: pick an action (the list comes from your server and shows the level each one needs), write its arguments as JSON, press Run. If the session is too weak she says so before sending anything. Critical actions, the ones that can change or delete things, ask once more.
- **Master Control**: "Check the PC" reads the PC's own Master file through a short Look-only session (5 minutes, ended right after). "Attach Master Session" gives this window Full authority while Master Control is ON at the PC. It can only be turned on at the PC: `iras --master-enable 30`. Nothing here can turn it on.
- Safety: pictures and results are cleared when you leave the screen or end the session. The session key stays in this window only, under the same name the old page uses. Every question is asked inside the page, with no browser pop-ups.
- Server: one new read-only address, `GET /v1/remote/policy` (needs your token). It tells the screen your server's highest level and the permission each action needs. Nothing else changed on the server. The Windows app and the PC side are unchanged.

## Who is here (new): the first step of multi-user recognition
- A small pill on Home and Chat says who is talking. Tap it: pick a person she knows ("I am Alice"), "A guest is here", "Nobody in particular", or go to check your face or voice. Face ID and Voice ID set it by themselves when they recognise someone. Ctrl+K has "Who is here?" and "A guest is here" too.
- A recognised or picked person is kept for 30 minutes, in this window only. A guest stays until you clear it. She never forgets a guest on her own, because that would quietly give a visitor your private things.
- Chat sends only the person's id and how she knew (face, voice or picked), never the name. The server accepts only a person it already knows and looks up the name itself, so the page cannot write her instructions. A made-up id is ignored.
- What she does with it: she uses the name now and then. She is told it is a hint, not proof, and that it never unlocks an approval. In guest mode her remembered facts are left out of her prompt, and she is told to keep your private things (facts, calendar, reminders, messages, files, accounts) private, and that a guest cannot approve anything.
- Be clear about the limit: guest mode is a strong request to her plus no remembered facts in her prompt. It is not a lock. She can still use her tools.
- Not done yet, so the next steps: each person's own memory, calendar and reminders, and checking the speaker's voice by itself during voice chat.
- Server: an optional `speaker` field on `/v1/chat` and `/v1/chat/stream`. New file `src/iras/identity/context.py`. The assistant takes the hint for one request and puts it back after. If a chat has no hint, nothing changes. The audit log keeps the person id and how she knew, not the name.

## Check everything (new): for test day
- Settings, new card **Check everything** (also in Ctrl+K). One press asks your server and your browser twelve questions: the server, your access token, the AI, the database, her voice, Face ID, Voice ID, your calendar, your PC, the microphone, the camera, and listening. Each line is OK, "look at this" or a problem, and says in plain words what to do.
- It changes nothing. It makes one tiny speech request (the word "Checking my voice.") and plays no sound. Press "Test her voice" to listen.
- The database line is the important one for Render: it tells you if the server is really connected to Supabase, or quietly using temporary storage that is lost on every restart. It uses the server's own `/ready` answer and its help text.
- The calendar line reads the next 7 days from your private link, so it also tests your Google link.
- If the server cannot be reached, or the token is refused, the lines that depend on it are skipped, so you see the first real problem and not a pile of errors.
- **Copy report** puts a plain-text report on the clipboard: the time, your server's name, your browser, and every line. It never holds your token or your full address. Paste it to me.
- Nothing runs by itself. It only runs when you press the button.

## Phone top bar (a fix)
- Your original page had a top bar that was 18 px too wide at 390 px and 48 px too wide at 360 px, as soon as the database was healthy (the "Cloud database" chip shows). It now fits phones from 360 px up, also with a PC session or a guest shown. Under 520 px the word "IRAS" is hidden (the orb stays). With a PC session open the storage chip is hidden, and under 360 px it is hidden too.

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
`python -m pytest tests/test_gemini_tts.py tests/test_reminders.py tests/test_identity.py tests/test_voice.py tests/test_agenda.py tests/test_speaker_context.py tests/test_command_center_ui.py tests/test_remote_policy_catalog.py tests/test_remote_web_direct_v400.py tests/test_remote_web_security_v400.py tests/test_master_control_rc3.py`
(The last three were failing before, because they read the web page for the remote tools. They pass again. `test_master_control_rc3.py` now reads the Android file `ClassicActivity.java`, where the native screen lives since the Android app became a web view. `test_command_center_ui.py` now checks the real page, `clients/web/index.html`, instead of an old copy in the `command-center` folder. It also catches a stale page.)
(`test_voice.py` runs the real voice model only if the model file is already on your computer. It never downloads anything.)
