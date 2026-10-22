# Her new voice (Gemini)

1. In Render, open your service, then Environment. Check that `GEMINI_API_KEY` is set (the same key her chat brain uses).
2. Optional: add `IRAS_TTS_ENGINE` = `gemini`, so every screen (the old page too) uses the new voice.
3. Optional: add `IRAS_GEMINI_VOICE` = `Leda`. Other girl voices to try: `Aoede`, `Sulafat`, `Zephyr`, `Despina`, `Vindemiatrix`.
4. Deploy. Open the new screen, go to Settings, then Voice, pick "Human · Gemini Leda", and press "Test her voice".

If Gemini fails, she uses the old voice and the test message tells you why (no key, limit reached, and so on).
Models: `IRAS_GEMINI_TTS_MODEL` is `gemini-3.8-flash-lite-tts` by default (fast). `gemini-3.8-flash-tts` is richer but slower.
Tests: `python -m pytest tests/test_gemini_tts.py`
