import os

import numpy as np

from iras.voice.multilingual_voice import whisper_language_hint
from iras.voice.stt import Listener


class _Default:
    device = (0, -1)


class FakeWindowsSD:
    default = _Default()

    def __init__(self):
        self.devices = [
            {
                "name": "Microphone (WO Mic Device)",
                "max_input_channels": 1,
                "default_samplerate": 48000.0,
                "hostapi": 2,
            },
            {
                "name": "Microphone (Realtek(R) Audio)",
                "max_input_channels": 2,
                "default_samplerate": 44100.0,
                "hostapi": 0,
            },
            {
                "name": "Microphone Array (Realtek(R) Audio)",
                "max_input_channels": 2,
                "default_samplerate": 48000.0,
                "hostapi": 1,
            },
            {
                "name": "Stereo Mix (Realtek(R) Audio)",
                "max_input_channels": 2,
                "default_samplerate": 48000.0,
                "hostapi": 1,
            },
        ]
        self.hostapis = [
            {"name": "MME"},
            {"name": "Windows WASAPI"},
            {"name": "Windows DirectSound"},
        ]

    def query_devices(self, device=None, kind=None):
        if device is None and kind is None:
            return self.devices
        if device is None:
            device = self.default.device[0]
        if isinstance(device, str):
            for item in self.devices:
                if device.casefold() in item["name"].casefold():
                    return item
            raise ValueError(device)
        return self.devices[int(device)]

    def query_hostapis(self, index):
        return self.hostapis[int(index)]


def test_auto_microphone_prefers_realtek_wasapi_over_default_wo_mic(monkeypatch):
    monkeypatch.delenv("IRAS_MIC_DEVICE", raising=False)
    fake = FakeWindowsSD()
    ranked = Listener.ranked_input_devices(fake)
    assert ranked[0]["index"] == 2
    assert ranked[0]["hostapi"] == "Windows WASAPI"
    assert Listener.select_input_device(fake) == 2


def test_explicit_microphone_still_wins_over_auto_ranking(monkeypatch):
    monkeypatch.setenv("IRAS_MIC_DEVICE", "1")
    assert Listener.select_input_device(FakeWindowsSD()) == 1


def test_named_realtek_selection_resolves_duplicate_name_by_best_host_api(monkeypatch):
    fake = FakeWindowsSD()
    fake.devices[2]["name"] = "Microphone (Realtek(R) Audio)"
    monkeypatch.setenv("IRAS_MIC_DEVICE", "Microphone (Realtek(R) Audio)")
    assert Listener.select_input_device(fake) == 2


def test_roman_urdu_stt_remains_multilingual_unless_explicitly_forced(monkeypatch):
    monkeypatch.setenv("IRAS_LANGUAGE", "roman-urdu")
    monkeypatch.setenv("IRAS_STT_LANGUAGE", "auto")
    assert whisper_language_hint() is None

    monkeypatch.setenv("IRAS_STT_LANGUAGE", "ur")
    assert whisper_language_hint() == "ur"

    monkeypatch.setenv("IRAS_STT_LANGUAGE", "en")
    assert whisper_language_hint() == "en"


def test_wake_word_accepts_common_whisper_iras_variants():
    assert Listener._contains_wake("Iris open Chrome", ("iras",))
    assert Listener._contains_wake("Eris play Spotify", ("iras",))
    assert Listener._contains_wake("I R A S open settings", ("iras",))
    assert Listener._contains_wake("آئرس کروم کھولو", ("iras",))
    assert Listener._strip_wake("Iris, open Chrome", ("iras",)) == "open Chrome"


def test_first_speech_block_is_not_used_as_noise_floor():
    class FakeSD:
        class _Stream:
            def __init__(self, callback):
                self.callback = callback

            def __enter__(self):
                speech = np.full((480, 1), 0.020, dtype="float32")
                silence = np.zeros((480, 1), dtype="float32")
                self.callback(speech, len(speech), None, None)
                self.callback(speech, len(speech), None, None)
                self.callback(silence, len(silence), None, None)
                self.callback(silence, len(silence), None, None)
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def query_devices(self, device=None, kind=None):
            if device is None and kind is None:
                return [{
                    "name": "Microphone Array (Realtek(R) Audio)",
                    "max_input_channels": 1,
                    "default_samplerate": 16000.0,
                    "hostapi": 0,
                }]
            return {
                "name": "Microphone Array (Realtek(R) Audio)",
                "max_input_channels": 1,
                "default_samplerate": 16000.0,
                "hostapi": 0,
            }

        def query_hostapis(self, index):
            return {"name": "Windows WASAPI"}

        def check_input_settings(self, **kwargs):
            return None

        def InputStream(self, **kwargs):
            return self._Stream(kwargs["callback"])

    listener = Listener()
    captured = listener._capture_phrase_on_device(
        np,
        FakeSD(),
        device=0,
        start_timeout=0.2,
        max_seconds=0.5,
        silence_seconds=0.03,
        min_speech_seconds=0.0,
        energy_threshold=0.004,
        noise_multiplier=2.6,
        sample_rate=16000,
    )
    assert captured is not None
    audio, rate = captured
    assert rate == 16000
    assert float(np.max(np.abs(audio))) >= 0.019
    assert listener.last_energy_threshold <= 0.0041


def test_web_hands_free_cycles_multilingual_recognition_locales():
    from pathlib import Path

    text = Path("clients/web/index.html").read_text(encoding="utf-8")
    assert 'const locales=["en-IN","ur-PK","en-US",navigator.language||""];' in text
    assert "function advanceSpeechLocale()" in text
    assert 'if(code==="language-not-supported")' in text
    assert '"آئرس"' in text
    assert '"ایرس"' in text


def test_android_hands_free_has_language_detection_and_retry_cycle():
    from pathlib import Path

    text = Path(
        "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java"
    ).read_text(encoding="utf-8")
    assert 'candidates.add("en-IN");' in text
    assert 'candidates.add("ur-PK");' in text
    assert 'candidates.add("en-US");' in text
    assert '"android.speech.extra.ENABLE_LANGUAGE_DETECTION"' in text
    assert '"android.speech.extra.LANGUAGE_DETECTION_ALLOWED_LANGUAGES"' in text
    assert "recognitionRunning =\n                true;\n            recognizer.startListening" in text
    assert '"آئرس"' in text
    assert '"ایرس"' in text
