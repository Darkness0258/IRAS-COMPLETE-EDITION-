# IRAS test day

One checklist for everything that only you can try, because it needs your own devices.
Do the steps **in this order**. Each step needs the ones before it.
Tick each box. After each step write one word: **OK**, or what went wrong.
At the end, send me the short block at the bottom ("Send me this").

**You need**

- Your PC with Chrome or Edge, a webcam and a microphone, in a quiet room.
- Your phone (Android).
- Your Render page, and your GitHub page.
- Your `IRAS_API_TOKEN` (Render, your service, Environment).
- If you can: one other person for the Face ID and Voice ID steps. It proves she can tell two people apart.

**Never send me** the access token, the Gemini key, the OpenRouter key or your calendar link. They are secrets.
The report that "Copy report" makes does not contain them. Check it before you paste it.

---

## 1. Put it live on Render (10 minutes)

- [ ] Do "Put it live" in `UPDATE-NOTES.md` (unzip, `git add`, `git commit`, `git push`).
- [ ] Render: your service shows the new deploy as **Live**. (On the free plan the server sleeps. The first page can take about a minute.)
- [ ] Open your site and press **Ctrl+F5**.
- [ ] **Settings**, **Connection**: "Server address" is your Render address, "Access token" is your `IRAS_API_TOKEN`. Press **Test connection**.
- You should see: it says it is connected, and the header chip says **Synced**.
- If not: tell me what it says, and the last 20 lines of the Render log (without secrets).

## 2. Start the two builds now (2 minutes, then they build while you test)

The apps show the same screen as the website, so they already have the new screens once Render is live.
This push does not start the builds (nothing in the Android or Windows files changed), so start them by hand. They take a few minutes.

- [ ] GitHub, **Actions**, **Build Android APK**, **Run workflow** (branch `main`).
- [ ] GitHub, **Actions**, **Build Windows EXE**, **Run workflow** (branch `main`).
- You will use them in step 11.

## 3. Check everything (5 minutes)

- [ ] **Settings**, **Check everything**, press **Run checks**.
- You should see one line each for: Server, Access token, AI, Database, Her voice, Face ID, Voice ID, Calendar, **Right now**, Your PC, Microphone, Camera, Listening.
- Each line says OK, "look at this", or a problem, and says what to do. "Look at this" is fine for things you have not set up yet (for example Calendar).
- The **Database** line is the important one: it must say your Supabase database is connected, not temporary storage.
- **Right now** must say it works.
- [ ] Press **Copy report**, and keep it. You will paste it at the end.
- If a line is a problem: tell me the line. That is enough.

## 4. Her voice (Gemini) (5 minutes)

- [ ] Render, Environment: `GEMINI_API_KEY` is there. (Do not send it to me.)
- [ ] **Settings**, **Voice**, "Voice identity": pick **Human · Gemini Leda (youthful)**. Press **Test her voice**.
- You should hear a natural voice, not the robot voice.
- [ ] **Check everything**: the **Her voice** line is OK.
- Optional: in Render add `IRAS_GEMINI_VOICE` with `Aoede`, `Sulafat`, `Zephyr` or `Despina`, and listen again.

## 5. Your calendar link (10 minutes)

- [ ] In Google Calendar, open the settings of your calendar and copy the **Secret address in iCal format**. It is a secret, like a password.
- [ ] **Agents**, **Calendar**, press **Add**. Paste it into "Secret iCal link". Leave "Whose calendar?" on yours (or "Everyone"). Press **Add calendar**.
- You should see: "Calendar added: N events in the next 7 days. I will remind you 10 minutes before each one."
- [ ] N matches what Google shows for the next 7 days.
- [ ] The link box is empty when you open it again.
- [ ] **Check everything**, **Calendar**: OK.
- [ ] Optional (15 minutes): make an event that starts in about 12 minutes. Keep the page open with the sound on. About 10 minutes before it starts she says it out loud and shows a message.

## 6. Face ID with the webcam (15 minutes)

- [ ] **Identity**, **Start camera**. Allow the camera. (The first picture downloads two small face models. Wait for it.)
- [ ] Write your name in "Your name". Press **Teach her my face**. Turn your head a little between the 5 pictures.
- [ ] Press **Who is this?** with your face. You should see your name and a score of **0.45 or more**.
- [ ] Cover the camera, or let another person look into it. She must **not** say your name.
- [ ] If you have a second person: teach their face too. Each one must be named correctly, one after the other.
- [ ] Go to **Home**: "Who is here" shows your name with **face**.
- If she says "not sure" when it is you: tell me the score she shows, and the light in the room.
- If the server restarts while you use Face ID: tell me. (Render's free plan has 512 MB of memory.)

## 7. Voice ID with your microphone (15 minutes)

- [ ] **Identity**, **Voice ID**. Write your name. Press **Teach her my voice**. Read the 3 lines out loud, about 8 seconds each.
- [ ] Press **Who is speaking?** and talk for 6 seconds. You should see your name and a percent of **50% or more**.
- [ ] Let another person press it and talk. She must **not** say your name.
- If she says "not sure" when it is you: tell me the percent. Your own microphone may score lower than my test did.
- If the server restarts while you use Voice ID: tell me.

## 8. The voice check while you talk (update 7) (10 minutes)

This needs step 7 (a taught voice). Use Chrome or Edge on your PC. It uses your real microphone and Chrome's real speech recognition together. I could not test that.

- [ ] **Settings**, **Voice**: "Know who is speaking by voice" is on. (On a computer it is on by itself.)
- [ ] On **Home**, press the mic (or Space). Say a full sentence, about 3 seconds.
- You should see: the "who is here" pill says your name and **voice**, and **Activity** has a line "Checked who is speaking".
- [ ] The header "Mic" chip goes off when you stop talking.
- [ ] Say a very short word ("hi"). Nothing should change (too little speech).
- [ ] If you have a second person: let them say a sentence. The pill should change to them.
- [ ] Switch to **A guest is here** and talk. She must not change guest mode and must not record.
- Not a problem: in the Android app the check is always off. Settings says so.
- If nothing happens: **Check everything**, read the **Voice ID** line, and tell me what it says.

## 9. Right now (update 8) (15 minutes)

You need step 5 (your calendar). Use **Home** on your PC.

- [ ] The **Right now** card is above **Live activity**, with four rows: Time, Who is here, Next event, Reminders due.
- [ ] **Time** matches the clock of your PC. **Next event** matches your Google Calendar ("in 25 min · 4:45 PM").
- [ ] **Agents**, **Remind me**: "What should she remind you about?" = `test`, "When?" = `in 30 minutes`, "For" = you. Press **Set reminder**.
- [ ] Back on **Home**, within a minute the reminder shows in **Reminders due**.
- [ ] Press the "who is here" pill and pick a different person (or **A guest is here**). The card must stop showing the first person's things at once. For a guest it shows only the time, and "Hidden for a guest" on the other two rows.
- [ ] Ask her: "What is my next event?" and "What time is it for me?". With the switch on she should answer like the card. (She may also use a tool to read the clock. That is fine.)
- [ ] As a guest ask: "What is on my calendar?" She must not tell you.
- [ ] **Settings**, **Right now**, switch "Tell her what is going on around her" off. The card disappears from Home. **Check everything** says the **Right now** line is switched off. Switch it on again.
- [ ] Phone (browser or app): a tall phone shows **one line** with an arrow. A short phone shows a small **clock button** in the Live activity row. Both open the same card. **Escape** or the arrow closes it.
- Please know: with the switch on, the title of your next event and the text of your due reminders go to the AI model inside your message. A guest's never do.

## 10. The update 6 screens, on the website (15 minutes)

You need two people (steps 6 and 7). If nobody else is there, teach a second name with your own face, only for this test. Face ID will then say "not sure" for you. Do this step last, and forget the second name afterwards with the bin buttons.

- [ ] **Memory**, "What should IRAS remember?": write `I like green tea`, "Whose memory?" = person one. **Save to memory**. Do it again for person two.
- [ ] The list says whose each memory is. "Show" lets you see one person's memories only.
- [ ] **Identity**, "Each person's own memories": try **Make the old memories mine** and **Share all of their memories**. It tells you how many moved.
- [ ] **Agents**, **Remind me**, "For" = person one, in 2 minutes. When it comes, with person one here you see the text. With person two or a guest here you only see "A private reminder for <name> is due", and nothing is spoken.
- [ ] **Agents**, **Calendar**: a calendar with "Whose calendar?" = person one is shown on the **Right now** card only when person one is here.

## 11. The apps (30 minutes)

**Android**

- [ ] GitHub, **Actions**, the finished **Build Android APK** run, download **IRAS-Android-APK**, unzip, install `app-debug.apk`. Your phone may ask you to allow installing from your files app or browser. If it says "App not installed", delete the old IRAS app first.
- [ ] Open it. If it asks for the server address and the access token, use the same as in step 1.
- [ ] Home loads and shows the **Right now** card (a short phone shows the clock button).
- [ ] The phone asks for the microphone and the camera when you use them. Voice chat works with the phone's own speech recognizer.
- [ ] **Memory**, **Identity**, **Agents** and **Settings**, **Check everything** open without an error. **Copy report** works.
- [ ] Step 10 in short: a reminder "For" one person is private for the other.

**Windows**

- [ ] GitHub, **Actions**, the finished **Build Windows EXE** run, download **IRAS-Windows-EXE**, unzip, run `IRAS.exe`. If Windows warns that the publisher is unknown (the file is not signed), choose "More info", then "Run anyway".
- [ ] Press **Command Center**. The new screen opens in its own window and you are signed in.
- [ ] Home, Memory, Identity, Agents and **Check everything** open without an error.
- [ ] Face ID (camera) and Voice ID (microphone) work inside this window.

## If something goes wrong

1. Press **Check everything**, **Run checks**, **Copy report**.
2. Write what you pressed, and what you expected.
3. Send me the report and a screenshot. Never the token, the keys or the calendar link.

---

## Send me this

```
Test day results
1  Render deploy:
2  Builds started:
3  Check everything (paste the report):
4  Gemini voice:
5  Calendar:
6  Face ID (score when it is me / when it is not):
7  Voice ID (percent when it is me / when it is not):
8  Voice check while I talk:
9  Right now (card, switch, guest, phone):
10 Update 6 screens (website):
11 Android app:
11 Windows app:
```
