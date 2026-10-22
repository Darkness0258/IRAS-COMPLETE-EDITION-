# IRAS update

## Put it live (website)
1. Unzip into your IRAS folder. Run `git status` and check that `.env` is not in the list.
2. `git add clients src tests UPDATE-NOTES.md`, then `git commit -m "Update"`, then `git push`.
3. After Render finishes the deploy, open the site and press Ctrl+F5.

## Phone and PC, the quick way (no rebuild)
- Phone (Chrome): open the site, menu, "Install app". PC (Edge or Chrome): the install icon in the address bar. They open in their own window and always show the newest screen.

## Android app (new screen inside the app)
- The push also starts "Build Android APK" on GitHub (Actions). Download `IRAS-Android-APK`, install it.
- If the phone says "App not installed", uninstall the old IRAS first, then install the new one. Have your token ready.
- The app now shows the same screen as the website. Her ears are the phone's own speech recognizer.
- The old native screen is still inside the app. On the "Cannot reach IRAS" page, press "Open the classic screen".

## Windows app
- The push also starts "Build Windows EXE". Download `IRAS-Windows-EXE`.
- New button "Command Center": opens the new screen in its own window and signs you in with the saved token.
  (The token is passed in the address part after # so the server never sees it. It is briefly visible in that window's command line on your PC.)

## Her new voice (Gemini)
- In Render, Environment: check `GEMINI_API_KEY` is set. Optional: `IRAS_TTS_ENGINE` = `gemini` and `IRAS_GEMINI_VOICE` = `Leda` (try `Aoede`, `Sulafat`, `Zephyr`, `Despina`).
- New screen: Settings, Voice, pick "Human · Gemini Leda", press "Test her voice".

## Reminders
- Agents, Routines, "Remind me": "in 10 minutes", "at 5pm", "tomorrow at 9". She shows a notice and says it out loud (page open, checks every 20 seconds).

## Tests
`python -m pytest tests/test_gemini_tts.py tests/test_reminders.py`
