from pathlib import Path

import pytest

from iras.voice.multilingual_voice import detect_language, resolve_voice


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello, how are you today?", "en"),
        ("Bonjour, je vais bien merci.", "fr"),
        ("Hola, c\u00f3mo est\u00e1s? Estoy muy bien.", "es"),
        ("Hallo, wie geht es dir?", "de"),
        ("Ciao, come stai? Io sto bene.", "it"),
        ("Ol\u00e1, como voc\u00ea est\u00e1?", "pt"),
        ("Merhaba, nas\u0131ls\u0131n?", "tr"),
        ("Hallo, hoe gaat het met jou?", "nl"),
        ("Cze\u015b\u0107, jak si\u0119 masz?", "pl"),
        ("Xin ch\u00e0o, b\u1ea1n kh\u1ecfe kh\u00f4ng?", "vi"),
        ("Halo, apa kamu baik?", "id"),
    ],
)
def test_roman_urdu_mode_does_not_hijack_other_latin_languages(text, expected):
    code, confidence, reason = detect_language(text, preferred="roman-urdu")
    assert code == expected
    assert confidence >= 0.58
    assert reason != "roman-urdu-default"


def test_unknown_latin_text_defaults_to_english_not_urdu():
    code, _, reason = detect_language(
        "Quantum scheduler online and ready.",
        preferred="roman-urdu",
    )
    assert code == "en"
    assert reason == "latin-default-under-roman-urdu"


def test_roman_urdu_latin_uses_south_asian_latin_voice(monkeypatch):
    monkeypatch.setenv("IRAS_ROMAN_URDU_VOICE", "en-IN-NeerjaNeural")
    selection = resolve_voice(
        "Main theek hoon, aap sunao kya chal raha hai?",
        preferred_language="roman-urdu",
    )
    assert selection.language == "ur"
    assert selection.locale == "en-IN"
    assert selection.label == "Roman Urdu (Latin)"
    assert selection.voice == "en-IN-NeerjaNeural"
    assert selection.gender == "female"
    assert selection.reason == "roman-urdu-markers"


def test_native_urdu_script_still_uses_native_urdu_voice():
    selection = resolve_voice(
        "\u0645\u06cc\u06ba \u0679\u06be\u06cc\u06a9 \u06c1\u0648\u06ba\u060c \u0622\u067e \u0633\u0646\u0627\u0626\u06cc\u06ba\u061f",
        preferred_language="roman-urdu",
    )
    assert selection.language == "ur"
    assert selection.locale == "ur-PK"
    assert selection.voice == "ur-PK-UzmaNeural"
    assert selection.reason == "urdu-script"


def test_native_arabic_and_hindi_keep_native_voices():
    arabic = resolve_voice(
        "\u0645\u0631\u062d\u0628\u0627\u060c \u0643\u064a\u0641 \u062d\u0627\u0644\u0643\u061f",
        preferred_language="roman-urdu",
    )
    hindi = resolve_voice(
        "\u0928\u092e\u0938\u094d\u0924\u0947\u060c \u0906\u092a \u0915\u0948\u0938\u0947 \u0939\u0948\u0902\u061f",
        preferred_language="roman-urdu",
    )
    assert arabic.language == "ar"
    assert arabic.voice == "ar-SA-ZariyahNeural"
    assert hindi.language == "hi"
    assert hindi.voice == "hi-IN-SwaraNeural"


def test_web_separates_recognition_from_roman_urdu_fallback_tts():
    text = Path("clients/web/index.html").read_text(encoding="utf-8")
    assert 'if(selected==="roman-urdu")return "ur-PK";' in text
    assert "function ttsFallbackLocale()" in text
    assert 'if(selected==="roman-urdu")return "en-IN";' in text
    assert "utterance.lang=ttsFallbackLocale();" in text
    assert "r.lang=speechLocale();" in text


def test_android_separates_recognition_from_local_tts():
    text = Path(
        "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java"
    ).read_text(encoding="utf-8")
    assert 'if (configured.equalsIgnoreCase("roman-urdu")) return "ur-PK";' in text
    assert "private String ttsLanguage()" in text
    assert 'if (configured.equalsIgnoreCase("roman-urdu")) return "en-IN";' in text
    assert "ttsLanguage()" in text
    assert "speechLanguage()" in text


def test_env_exposes_roman_urdu_voice_override():
    text = Path(".env.example").read_text(encoding="utf-8")
    assert "IRAS_ROMAN_URDU_VOICE=en-IN-NeerjaNeural" in text
