from pathlib import Path


def test_windows_cloud_client_has_real_voice_io():
    text = Path("src/iras/cloud_client.py").read_text(encoding="utf-8")
    assert "from iras.voice.stt import Listener" in text
    assert "from iras.voice.tts import Speaker" in text
    assert '"/voice test"' in text
    assert '"/listen"' in text
    assert '"voice"' in text
    assert "speaker.speak(reply_text)" in text


def test_android_requests_mic_and_has_native_tts_fallback():
    text = Path(
        "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java"
    ).read_text(encoding="utf-8")
    assert "initLocalTts();" in text
    assert "TextToSpeech localTts" in text
    assert "speakLocally(" in text
    assert "Microphone permission denied" in text
    assert "ERROR_INSUFFICIENT_PERMISSIONS" in text
    assert "this::startHandsFreeListening" in text


def test_android_cloud_registration_matches_rc12():
    text = Path(
        "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java"
    ).read_text(encoding="utf-8")
    assert 'registration.put("app_version", "5.0.0-rc12");' in text


def test_web_has_browser_tts_fallback_and_barge_in_cancel():
    text = Path("clients/web/index.html").read_text(encoding="utf-8")
    assert "async function browserSpeak" in text
    assert "SpeechSynthesisUtterance" in text
    assert "window.speechSynthesis.cancel()" in text
    assert "using browser TTS" in text


def test_cloud_tts_has_health_and_female_fallback():
    text = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    assert '@app.get("/v1/voice/health")' in text
    assert '"en-US-JennyNeural"' in text
    assert '"X-IRAS-Voice-Fallback"' in text
    assert "IRAS voice generation failed: " in text

def test_cli_module_executes_main_and_desktop_uses_configured_profile():
    cli = Path("src/iras/cli.py").read_text(encoding="utf-8")
    desktop = Path("src/iras/desktop.py").read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in cli
    assert "main()" in cli.split('if __name__ == "__main__":', 1)[1]
    assert "self.settings.voice_profile" in desktop


def test_web_and_android_report_current_rc12_version():
    web = Path("clients/web/index.html").read_text(encoding="utf-8")
    android = Path(
        "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java"
    ).read_text(encoding="utf-8")
    assert 'app_version:"5.0.0-rc12"' in web
    assert 'registration.put("app_version", "5.0.0-rc12");' in android


def test_android_stops_recognition_during_playback_and_restarts_afterward():
    text = Path(
        "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java"
    ).read_text(encoding="utf-8")
    play_voice = text.split("private void playVoice(", 1)[1].split(
        "private void stopVoice()", 1
    )[0]
    assert "stopRecognition();" in play_voice
    assert "resumeHandsFreeAfterVoice(" in play_voice
    stop_voice = text.split("private void stopVoice()", 1)[1].split(
        "private String cloudClientId()", 1
    )[0]
    assert "localTts.stop();" in stop_voice
    assert "resumeHandsFreeAfterVoice(" in text


def test_listener_falls_back_to_supported_input_sample_rate():
    from iras.voice.stt import Listener

    class FakeSD:
        def __init__(self):
            self.checked = []

        def check_input_settings(self, **kwargs):
            self.checked.append(kwargs["samplerate"])
            if kwargs["samplerate"] == 16000:
                raise RuntimeError("unsupported")

        def query_devices(self, device, kind):
            assert kind == "input"
            return {"default_samplerate": 44100.0}

    fake = FakeSD()
    assert Listener._supported_sample_rate(fake, 16000) == 44100
    assert fake.checked == [16000, 44100]

def test_android_manifest_declares_speech_and_tts_service_queries():
    text = Path("clients/android/app/src/main/AndroidManifest.xml").read_text(
        encoding="utf-8"
    )
    assert "android.speech.RecognitionService" in text
    assert "android.intent.action.TTS_SERVICE" in text

def test_voice_preferences_persist_in_android_and_web_clients():
    android = Path(
        "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java"
    ).read_text(encoding="utf-8")
    web = Path("clients/web/index.html").read_text(encoding="utf-8")
    assert '.putString(\n                            "speech_language",' in android
    assert '.putString(\n                            "voice_mood",' in android
    persist = web.split("function persistHandsFree()", 1)[1].split(
        "function updateHandsButton()", 1
    )[0]
    assert "...stored" in persist
    assert "language" not in persist or "stored" in persist

