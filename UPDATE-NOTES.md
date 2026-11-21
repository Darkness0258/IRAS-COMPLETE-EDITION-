# IRAS update

## Put it live
1. Unzip into your IRAS folder. Run `git status` and check that `.env` is not in the list.
2. `git add clients src tests pyproject.toml Dockerfile UPDATE-NOTES.md`, then `git commit -m "Update"`, then `git push`.
3. Render rebuilds (the first build is longer, it installs the Face ID and calendar packages). Then open the site and press Ctrl+F5.
4. This push does not start the Android or Windows builds, because nothing in them changed. The phone and PC apps show the same screen, so they get the new screens as soon as Render is live.

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
- Done in a later update: each person's own memory, calendar and reminders (see "Each person's own memory, calendar and reminders: the screens"). Still open: checking the speaker's voice by itself during voice chat.
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

## Each person's own things: the server side
A single-user setup behaves exactly as before. The screens for it are in the next section.
- **Memory:** with a known person talking (see "Who is here"), she saves and uses that person's own facts and memories, plus the shared ones. Never anyone else's. A guest gets nothing remembered, and cannot save anything. With nobody named, only shared things. Nothing in the database changes shape: a person's facts are stored as `p:<person_id>:<key>`, and their memories in the namespace `person:<person_id>`. New file: `src/iras/identity/scope.py`. The model's tools `remember_fact`, `search_memory` and the `v5_memory_*` tools follow it, and so does her prompt.
- **Old things stay shared** until you claim them: `POST /v1/identity/people/{id}/claim-memory` makes the shared facts and memories belong to that person. `POST /v1/identity/people/{id}/share-memory` makes ALL of a person's memories shared again, including ones saved only for them. Her own settings (`iras.*`) are never claimed.
- **Memory list fix:** `/v1/v5/memory/search` with an empty search used to return nothing, so the Memory screen showed no memories until you searched. It now lists the newest.
- **Reminders for one person:** the marker can carry a person id, `[reminder:per_abc] text`. The notice is titled "Reminder for Alice". A reminder for everyone is exactly as before, also on the phone.
- **Calendars for one person:** each calendar can have an owner (a new `owner` column, added to your existing table by itself; your calendars stay shared). Its reminders are for that owner. `POST /v1/calendar/feeds` takes `owner`. `POST /v1/calendar/feeds/{id}/owner` changes it. `GET /v1/calendar/events?owner=` limits the list (left out: all, empty: shared, an id: that person's).
- **The screens** for all of this are in the next section.
- Tests: `tests/test_memory_scope.py` (49) and `tests/test_owned_reminders.py` (40).

## Each person's own memory, calendar and reminders: the screens (new)
- **Memory:** saving has a new choice, **Whose memory?** (Shared, or one person). It starts on the person who is here (Who is here), or on Shared when nobody is named. A new **Show** choice filters the list: All, Shared, or one person. Every memory says whose it is, in the list and on its card. "Shared" also takes in what she saved for the household under the name `shared`. The list headings are now `h2` (they were `h3`, which skipped a level).
- **Identity:** a new card **Each person's own memories**. Each person she knows has two buttons. **Make the old memories mine** gives that person the old memories and facts, the ones saved before she knew who was talking. **Share all of their memories** makes EVERY memory and fact of that person shared again, also the ones saved only for them. Both ask first, and the question says what moves (the Share question says ALL). Nothing is sent until you say yes. Afterwards the screen says how many memories and facts moved. Memories she saved for the household under the name `shared` are not moved by either button.
- **Agents:** **Remind me** is now a small form inside the page (no browser pop-up): what, when, and **For** (Everyone, or one person). Adding a calendar is a form too, with **Whose calendar?**. Both start on the person who is here. Each calendar in the list has its own **Whose calendar?** choice, to change it later (the server then makes its reminders again). Reminders say "For Alice" or "For everyone". Events say whose they are as soon as any calendar has an owner. The link box is emptied when the form closes, because the link is a secret.
- **The Agents lists** are now redrawn only when something changed. Before, they were redrawn every 5 seconds, which would have wiped out a choice you were making in the new list.
- **Private reminder notices:** a notice titled "Reminder for Alice" is shown and spoken only when Who is here is Alice, or nobody. For anyone else, or a guest, the screen shows only "A private reminder for Alice is due" (or "3 private reminders for Alice are due" when several wait), speaks nothing, and does not keep the text, only the notice's number. When Alice arrives (or you change Who is here) the page looks again within a second and shows it in full. A reminder for everyone is shown to all, also to a guest. The first look at the notices shows at most 3 in total, full and private together.
- **Limits:** this is not a lock. The Agents screen still lists the reminder text, and Activity keeps the text of a reminder after it was shown to its owner, for anyone who opens those screens on this device. The page matches by the name in the notice's title, so two people with the same name count as one. Notices only show while the page is open.
- **Server:** nothing changed. New file `clients/web/command-center/src/js/36-people.js`: the list of people that all these screens use.
- **Tests:** `tests/test_command_center_people_screens.py` (15), and a test in a real browser (next point).
- **Browser test** (new): `clients/web/command-center/qa/browser-test.cjs` with `qa/test_server.py`. It opens the real page in a real Chrome (puppeteer-core with @sparticuz/chromium) and checks the three screens, the private notices, phone widths 360, 390 and 412 px, axe-core accessibility in two looks, and a fake microphone file. My last run: **128 of 128 checks passed** (Memory 24, Identity 12, Agents 27, private notices 23, microphone 2, phone widths 360, 390 and 412 px 12 each, dark look 4). It runs real Chrome 153, so it is a better check than reading the code, but it is Chrome only.
  1. Install the tools in a folder OUTSIDE the project: `mkdir ~/iras-qa-tools && cd ~/iras-qa-tools && npm init -y && npm i puppeteer-core @sparticuz/chromium axe-core`. (Inside the project, a test that reads every web file would read them.)
  2. Start the test server: `python clients/web/command-center/qa/test_server.py --port 8765 --token-file /tmp/iras-qa-token`. It is your real server code on a new, empty data folder (no `.env` database is used), with one fixed calendar for any https link and a placeholder model setting. It writes a new token to the file and never prints it.
  3. Run: `QA_NODE_DIR=~/iras-qa-tools IRAS_TOKEN_FILE=/tmp/iras-qa-token node clients/web/command-center/qa/browser-test.cjs`. It makes people, memories, reminders and a calendar named "QA ..." and deletes them at the end. It refuses to run against a server that is not on this computer. Screenshots go to `QA_SHOTS`. `QA_ONLY=phone` runs only the parts with that word in their name.

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
`python -m pytest tests/test_gemini_tts.py tests/test_reminders.py tests/test_identity.py tests/test_voice.py tests/test_agenda.py tests/test_speaker_context.py tests/test_memory_scope.py tests/test_owned_reminders.py tests/test_command_center_ui.py tests/test_command_center_people_screens.py tests/test_remote_policy_catalog.py tests/test_remote_web_direct_v400.py tests/test_remote_web_security_v400.py tests/test_master_control_rc3.py`
(The last three were failing before, because they read the web page for the remote tools. They pass again. `test_master_control_rc3.py` now reads the Android file `ClassicActivity.java`, where the native screen lives since the Android app became a web view. `test_command_center_ui.py` now checks the real page, `clients/web/index.html`, instead of an old copy in the `command-center` folder. It also catches a stale page.)
(`test_voice.py` runs the real voice model only if the model file is already on your computer. It never downloads anything.)
