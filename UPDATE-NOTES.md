# IRAS update

## Put it live
1. Unzip into your IRAS folder. Run `git status` and check that `.env` is not in the list.
2. `git add clients src tests pyproject.toml Dockerfile UPDATE-NOTES.md`, then `git commit -m "Update"`, then `git push`.
3. Render rebuilds (the first build is longer, it installs the Face ID and calendar packages). Then open the site and press Ctrl+F5.
4. This push does not start the Android or Windows builds, because nothing in them changed. The phone and PC apps show the same screen, so they get the new screens as soon as Render is live.

## Right now (new, update 8): she knows what is going on around her
- **What it does:** for the person who is here, she now knows the time of day, who is here, the next calendar event and the reminders that are due. You see it on a **"Right now" card on Home**, and she gets **the same facts** with each message you send. It is the first small piece of "she knows each person better".
- **The card has four rows:**
  - **Time:** for example "Afternoon · 4:19 PM", with the date. It is the clock of the device you look at.
  - **Who is here:** the name, and how she knows (face, voice, or picked by hand). Press the row to change who is here.
  - **Next event:** the next event that has not started yet, from that person's calendars and the shared ones, looking 7 days ahead. It says when ("in 25 min · 4:45 PM"). With no calendar at all it says so and offers "Add one". An event that is already running, and all-day events, are not shown (see below).
  - **Reminders due:** reminders that are due now, late (up to one day), or due in the next **4 hours**. Up to three are listed, and it says how many more there are. The reminder that the calendar makes by itself before each event is not listed twice.
- **Who sees what** (the same rule as memory):
  - **A person:** the shared things and their own. Never anyone else's.
  - **Nobody picked:** only the shared things.
  - **A guest:** only the time of day. For a guest the server does not even read the calendar or the reminders. The card says "Hidden for a guest".
  - When the person changes, the card **at once** stops showing the old person's things ("Checking…") until the answer for the new person has come. A test checks this.
- **What she is given:** a few lines (about 600 letters at most), right after the "who is talking" message. The **server** writes them from its own clock, calendars and reminders. The screen sends only its time zone, so the screen cannot put its own sentences into her instructions. Event titles and reminder texts are cleaned, cut short and put in quotes, and she is told they are data, not instructions. She is told to use them only when they help (for example when you ask "what is next?"), not to read them out on every turn, and that they never unlock an approval. If a calendar does not answer in 1.5 seconds she does not wait: she is told "not available right now, do not guess".
- **Please know:** with the switch on, the title of your next event and the text of your due reminders go to the AI model inside the message, in the same way her remembered facts do. A guest's calendar and reminders never do.
- **The off switch:** Settings, **Right now**, "Tell her what is going on around her". It is on by itself. Off means: no card, the server is not asked, and your messages carry nothing about it. Like the other screen settings it belongs to this window or app.
- **On a phone** there is no height to spare, so:
  - on a tall phone (about 800 px or more) the card is **one line** above Live activity. It shows the most useful thing, for example your next reminder. Press the arrow to open the whole card.
  - on a shorter phone there is **no extra line** (the orb would slide under the top bar). A small **clock button** in the Live activity row opens the card instead. Escape closes it.
- **Check everything** (Settings) has a new line, **Right now**. It asks the server the same question as the card. It says OK, "look at this" (for example when a calendar does not answer in time) or "problem" (the server is too old to have Right now). It is skipped when the switch is off. The line only says words and counts, never an event title or a reminder text, because the report you copy is pasted to me.
- **A small fix on the way:** the "who is here" pill on Home read out a different text than the one you see, which a screen reader or voice control could not match. Now they match. It looks the same.
- **Change the 4 hours:** on Render, add `IRAS_RIGHT_NOW_REMINDER_HOURS` (for example `2` or `12`; allowed from 0.25 to 72).
- **Not in this piece, on purpose:** an event that is already running; all-day events; events more than 7 days away; showing another person's reminder as "a private reminder". The card asks again every minute, when you come back to Home, and when who is here changes. A reminder you just added shows within a minute, or when you come back to Home.
- **Server side:** new `GET /v1/right-now` (needs the token like the others). The chat accepts an optional `right_now` field (`tz` and `offset`). Older screens do not send it and nothing changes for them.

## Voice check while you talk (new, update 7)
- **What it does:** when you talk to her in voice chat, she now checks whose voice it is **by herself**. You do not press "Who is speaking?". If she knows the voice, **Who is here** changes to that person (it says "voice"), and the reply already uses that person's own memory, calendar and reminders. It needs at least one taught voice (Identity, Voice ID).
- **How:** while she listens, the page also records the same few seconds (the browser's speech recognition does not give out the sound). It sends them once to your server, to the same address the "Who is speaking?" button uses. The sound is dropped right after. Nothing is saved. The microphone is let go the moment you stop talking, and the header "Mic" chip shows it while it is on.
- **What the answer does:**
  - **A clear match** (the same test as the button: 0.50 and 0.06 ahead of the next person): Who is here becomes that person. A message says so ("I know your voice, Alice", or "I hear Bob now, not Alice").
  - **"Nobody I know"** (every taught voice scores under 0.30): once changes nothing. **Twice in a row**, and she stops using the name (it becomes "Who is here?" again, and that reply goes out with no name). She only does this for a person whose voice she has learned, so a person set by face or by hand, without a taught voice, is never dropped. A match in between starts the count again.
  - **Not sure, or too little speech** (she needs 2 seconds of real speech): nothing changes.
  - **Guest mode is never changed by a voice.** In guest mode she does not even record.
  - If you pick someone yourself while a check is still out, **your choice wins**.
- **She never makes you wait long.** In a talk longer than about 3.5 seconds she asks early, so the answer is already there when you stop. Otherwise she waits at most about 2 seconds for your server. If it is slower, she answers you anyway, and the answer is used for your next turn. **Stop wins:** if you press Stop while she is checking, nothing is sent.
- **You can see it:** every check is one line in Activity ("Checked who is speaking": who she thought, how sure). **Settings, Voice, "Know who is speaking by voice"** is the switch, with one sentence that says how it is doing. The same sentence is on the Voice ID line of Check everything.
- **Where it works:**
  - **A computer with Chrome or Edge: yes, on by itself.**
  - **A phone's browser: starts off,** because on some phones listening and recording at the same time do not work. You can switch it on to try it.
  - **The Android app: off, always.** The app listens with the phone's own speech recognizer, which does not share the microphone. I did not touch the Android or Windows files, so this push starts neither build.
  - If the microphone cannot be shared, or gives no sound twice in a row, or listening stops while the check records, she turns the check off for that window and tells you. Voice chat itself keeps working. The switch in Settings turns it on again.
  - The first sentence right after you open the page may not be checked: the list of who has a taught voice arrives a moment after the page opens.
- **Server:** one new word in the answer of `POST /v1/identity/voice/verify`: `verdict` (match, other, unsure, nobody or unheard). Nothing was removed, so an older page still works. A new page also works with an older server (it works the word out from the old answer). New optional setting: `IRAS_VOICE_OTHER` (default 0.30).
- **Files:** new `clients/web/command-center/src/js/39-autoid.js` (the whole check). Small changes in `38-voice.js` (start and end of listening), `36-people.js` (knows who has a taught voice), `80-settings.js` and `settings.html` (the switch), `81-check.js` (the sentence), `90-app.js`, `00-core.js` and `identity.html` (one line). On the server: `src/iras/identity/store.py` and `routes.py`. Rebuild the page after you change any of them: `python clients/web/command-center/build.py --check`.
- **Be clear about the limits:**
  - It is a hint, like all of Who is here. A voice can be played back from a recording. It never approves anything.
  - When someone else talks at the same time as you, your own voice can score low. In my test a known person scored as low as 0.07 when another person was as loud as them, and 0.24 when the other was a little quieter. That is why one "nobody I know" is not enough.
  - One sentence can slip through. The first sentence of a stranger is still answered under the old name (the first "nobody I know" only counts). The same is true for the first sentence of a new person when your server is slow.
  - A sentence with less than 2 seconds of speech cannot be checked.
- **My tests:**
  - **The model, on real voices** (a small public set of 5 speakers, clean sound; 2 of them taught): people she knows scored 0.45 to 0.84, also with noise and with phone-quality sound. Strangers scored 0.01 to 0.24. So the 0.30 line has room on both sides, for one person talking alone.
  - **Real Chrome 153 + your real server code + the real voice model + recordings of those real people played into the page's microphone.** Only the browser's speech-to-text and the chat reply were faked. Fangjun talks: she knew him (72% sure) and the chat already used his name. Leijun talks next: she switched. Two strangers in a row: she kept the name once and dropped it the second time. A 1.6-second clip: "too little speech", no change. The microphone was let go every time. A check took 0.1 to 0.6 seconds on this computer. On Render's small free plan it will be slower.
  - **Python:** `tests/test_voice_listen_along.py` (16, the server's new word, with made-up voices: no model needed) and `tests/test_command_center_listen_along.py` (19, the page's rules: nothing stored, no guest-mode change, the Android app left alone, the microphone always let go, the waiting limit). I broke these rules on purpose 12 times (for example: let a voice change guest mode, wait 10 seconds, forget to let go of the microphone) and a test caught every one.
  - **Real browser:** 52 new checks in `qa/browser-test.cjs` (sections "Voice check ..."). They cover a match, a long talk, another person, "nobody I know" once and twice, a person with no taught voice, a match in between, "not sure", an older server, a slow server, Stop, picking someone yourself meanwhile, guest mode, the switch, no taught voice, a silent microphone, a microphone that cannot be shared, listening that fails, the Android app, and a phone's browser at 360 px with axe-core. They use Chrome's fake microphone and a scripted server answer. `QA_ONLY="voice check"` runs only these.
  - **Everything:** the whole browser test passed **180 of 180** (the 128 from before and 52 new), with no message from the page. My full Python run, before and after my change: the same 41 failed and 1 error (the old tests; no new one), and 1220 passed instead of 1184. You counted 42 failed and 1 error on your PC, one more than mine, so one old test behaves differently there. The rule is the same: after you put update 7 in, your number must stay at 42 failed and 1 error, not go up.
- **Not tested, because I cannot** (it needs your devices): the real microphone together with Chrome's real speech recognition (here the speech recognizer is a fake), phones, the Android and Windows apps, Render's real speed, and your own microphone's scores. If she is often "not sure" when it is you, tell me the percent in the Activity line.
- **Try it:** 1. Teach your voice (Identity, Voice ID). 2. If you can, teach a second person. 3. On your PC, in Chrome, open Home, press the mic and say a full sentence (about 3 seconds). 4. The pill should say your name and "voice", and Activity should have a "Checked who is speaking" line. 5. Let the other person say a sentence: the pill should change. 6. If nothing happens, press Check everything and read the Voice ID line: it says why. Paste me that report and the Activity lines.

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
- On this screen the microphone is on only while a recording runs, and the header "Mic" chip shows it. Leaving the screen stops it. (Since update 7, voice chat can also record a few seconds for the voice check. See "Voice check while you talk".)
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
- Done in later updates: each person's own memory, calendar and reminders (see "Each person's own memory, calendar and reminders: the screens"), and checking the speaker's voice by itself during voice chat (see "Voice check while you talk").
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
- **Browser test** (new): `clients/web/command-center/qa/browser-test.cjs` with `qa/test_server.py`. It opens the real page in a real Chrome (puppeteer-core with @sparticuz/chromium) and checks the three screens, the private notices, phone widths 360, 390 and 412 px, axe-core accessibility in two looks, and a fake microphone file. My last run: **180 of 180 checks passed** (Memory 24, Identity 12, Agents 27, private notices 23, microphone 2, phone widths 360, 390 and 412 px 12 each, dark look 4, and 52 for the voice check while you talk). It runs real Chrome 153, so it is a better check than reading the code, but it is Chrome only.
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
`python -m pytest tests/test_gemini_tts.py tests/test_reminders.py tests/test_identity.py tests/test_voice.py tests/test_agenda.py tests/test_speaker_context.py tests/test_memory_scope.py tests/test_owned_reminders.py tests/test_voice_listen_along.py tests/test_command_center_ui.py tests/test_command_center_people_screens.py tests/test_command_center_listen_along.py tests/test_remote_policy_catalog.py tests/test_remote_web_direct_v400.py tests/test_remote_web_security_v400.py tests/test_master_control_rc3.py`
(The last three were failing before, because they read the web page for the remote tools. They pass again. `test_master_control_rc3.py` now reads the Android file `ClassicActivity.java`, where the native screen lives since the Android app became a web view. `test_command_center_ui.py` now checks the real page, `clients/web/index.html`, instead of an old copy in the `command-center` folder. It also catches a stale page.)
(`test_voice.py` runs the real voice model only if the model file is already on your computer. It never downloads anything.)
