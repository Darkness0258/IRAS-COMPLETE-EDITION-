from __future__ import annotations

from iras.voice.multilingual_voice import (
    LANGUAGES,
    detect_language,
    normalize_language,
    resolve_voice,
)


def test_urdu_script_routes_to_pakistani_voice():
    code, confidence, reason = detect_language("آپ کیسے ہیں؟ مجھے یہ کام کرنا ہے")
    assert code == "ur"
    assert confidence >= .9
    choice = resolve_voice("آپ کیسے ہیں؟")
    assert choice.locale == "ur-PK"
    assert choice.voice == "ur-PK-UzmaNeural"
    assert choice.direction == "rtl"


def test_roman_urdu_detection_and_calm_default():
    code, confidence, _ = detect_language("mujhe batao ye kaise karna hai")
    assert code == "ur"
    assert confidence >= .6
    choice = resolve_voice("mujhe batao ye kaise karna hai")
    assert choice.mood == "calm"
    assert choice.rate == "-8%"


def test_major_scripts_detect_without_external_dependency():
    assert detect_language("こんにちは、元気ですか")[0] == "ja"
    assert detect_language("안녕하세요 반갑습니다")[0] == "ko"
    assert detect_language("你好，很高兴见到你")[0] == "zh"
    assert detect_language("Привіт, як справи?")[0] == "uk"
    assert detect_language("Привет, как дела?")[0] == "ru"
    assert detect_language("ਸਤ ਸ੍ਰੀ ਅਕਾਲ")[0] == "pa"
    assert detect_language("नमस्ते, आप कैसे हैं?")[0] == "hi"


def test_latin_language_markers():
    assert detect_language("bonjour merci pour votre aide")[0] == "fr"
    assert detect_language("hola gracias por tu ayuda")[0] == "es"
    assert detect_language("hallo danke für deine hilfe")[0] == "de"


def test_preferred_language_overrides_detection():
    code, confidence, reason = detect_language("hello there", preferred="urdu")
    assert (code, confidence, reason) == ("ur", 1.0, "preferred-language")


def test_gender_alternate_and_english_profile_voice():
    female = resolve_voice("Hello there", english_voice="en-US-AriaNeural", gender="female")
    assert female.voice == "en-US-AriaNeural"
    male = resolve_voice("Hello there", english_voice="en-US-AriaNeural", gender="male")
    assert male.voice == "en-US-GuyNeural"
    assert male.alternate_voice == "en-US-AriaNeural"


def test_catalog_is_broad_and_aliases_are_stable():
    assert len(LANGUAGES) >= 20
    assert normalize_language("Urdu Pakistan") == "ur"
    assert normalize_language("zh-CN") == "zh"
    assert normalize_language("automatic") == "auto"
