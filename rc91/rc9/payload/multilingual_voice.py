from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import re
import unicodedata
from typing import Any


@dataclass(frozen=True, slots=True)
class LanguageVoice:
    code: str
    locale: str
    label: str
    female_voice: str
    male_voice: str
    direction: str = "ltr"


@dataclass(frozen=True, slots=True)
class VoiceSelection:
    language: str
    locale: str
    label: str
    voice: str
    alternate_voice: str
    gender: str
    mood: str
    rate: str
    pitch: str
    volume: str
    direction: str
    confidence: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# Curated standard Neural voices. They are intentionally conservative/stable
# Edge/Azure voice IDs rather than preview-only model names.
LANGUAGES: dict[str, LanguageVoice] = {
    "en": LanguageVoice("en", "en-US", "English", "en-US-JennyNeural", "en-US-GuyNeural"),
    "ur": LanguageVoice("ur", "ur-PK", "Urdu (Pakistan)", "ur-PK-UzmaNeural", "ur-PK-AsadNeural", "rtl"),
    "hi": LanguageVoice("hi", "hi-IN", "Hindi", "hi-IN-SwaraNeural", "hi-IN-MadhurNeural"),
    "ar": LanguageVoice("ar", "ar-SA", "Arabic", "ar-SA-ZariyahNeural", "ar-SA-HamedNeural", "rtl"),
    "pa": LanguageVoice("pa", "pa-IN", "Punjabi", "pa-IN-VaaniNeural", "pa-IN-OjasNeural"),
    "fa": LanguageVoice("fa", "fa-IR", "Persian", "fa-IR-DilaraNeural", "fa-IR-FaridNeural", "rtl"),
    "bn": LanguageVoice("bn", "bn-IN", "Bengali", "bn-IN-TanishaaNeural", "bn-IN-BashkarNeural"),
    "tr": LanguageVoice("tr", "tr-TR", "Turkish", "tr-TR-EmelNeural", "tr-TR-AhmetNeural"),
    "fr": LanguageVoice("fr", "fr-FR", "French", "fr-FR-DeniseNeural", "fr-FR-HenriNeural"),
    "es": LanguageVoice("es", "es-ES", "Spanish", "es-ES-ElviraNeural", "es-ES-AlvaroNeural"),
    "de": LanguageVoice("de", "de-DE", "German", "de-DE-KatjaNeural", "de-DE-ConradNeural"),
    "it": LanguageVoice("it", "it-IT", "Italian", "it-IT-IsabellaNeural", "it-IT-DiegoNeural"),
    "pt": LanguageVoice("pt", "pt-BR", "Portuguese", "pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"),
    "ru": LanguageVoice("ru", "ru-RU", "Russian", "ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural"),
    "uk": LanguageVoice("uk", "uk-UA", "Ukrainian", "uk-UA-PolinaNeural", "uk-UA-OstapNeural"),
    "ja": LanguageVoice("ja", "ja-JP", "Japanese", "ja-JP-NanamiNeural", "ja-JP-KeitaNeural"),
    "ko": LanguageVoice("ko", "ko-KR", "Korean", "ko-KR-SunHiNeural", "ko-KR-InJoonNeural"),
    "zh": LanguageVoice("zh", "zh-CN", "Mandarin Chinese", "zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural"),
    "vi": LanguageVoice("vi", "vi-VN", "Vietnamese", "vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"),
    "id": LanguageVoice("id", "id-ID", "Indonesian", "id-ID-GadisNeural", "id-ID-ArdiNeural"),
    "th": LanguageVoice("th", "th-TH", "Thai", "th-TH-PremwadeeNeural", "th-TH-NiwatNeural"),
    "pl": LanguageVoice("pl", "pl-PL", "Polish", "pl-PL-ZofiaNeural", "pl-PL-MarekNeural"),
    "nl": LanguageVoice("nl", "nl-NL", "Dutch", "nl-NL-ColetteNeural", "nl-NL-MaartenNeural"),
}


ALIASES: dict[str, str] = {
    "auto": "auto", "automatic": "auto",
    "english": "en", "en-us": "en", "en-gb": "en", "en": "en",
    "urdu": "ur", "urdu pakistan": "ur", "ur-pk": "ur", "ur": "ur",
    "hindi": "hi", "hi-in": "hi", "hi": "hi",
    "arabic": "ar", "ar-sa": "ar", "ar": "ar",
    "punjabi": "pa", "panjabi": "pa", "pa-in": "pa", "pa": "pa",
    "persian": "fa", "farsi": "fa", "fa-ir": "fa", "fa": "fa",
    "bengali": "bn", "bangla": "bn", "bn-in": "bn", "bn": "bn",
    "turkish": "tr", "tr-tr": "tr", "tr": "tr",
    "french": "fr", "fr-fr": "fr", "fr": "fr",
    "spanish": "es", "es-es": "es", "es": "es",
    "german": "de", "de-de": "de", "de": "de",
    "italian": "it", "it-it": "it", "it": "it",
    "portuguese": "pt", "pt-br": "pt", "pt": "pt",
    "russian": "ru", "ru-ru": "ru", "ru": "ru",
    "ukrainian": "uk", "uk-ua": "uk", "uk": "uk",
    "japanese": "ja", "ja-jp": "ja", "ja": "ja",
    "korean": "ko", "ko-kr": "ko", "ko": "ko",
    "chinese": "zh", "mandarin": "zh", "zh-cn": "zh", "zh": "zh",
    "vietnamese": "vi", "vi-vn": "vi", "vi": "vi",
    "indonesian": "id", "id-id": "id", "id": "id",
    "thai": "th", "th-th": "th", "th": "th",
    "polish": "pl", "pl-pl": "pl", "pl": "pl",
    "dutch": "nl", "nl-nl": "nl", "nl": "nl",
}


MOODS: dict[str, tuple[str, str, str]] = {
    # Slightly slower and a little lower: designed to reduce sharp/rushed output.
    "calm": ("-8%", "-2Hz", "+0%"),
    "warm": ("-4%", "+0Hz", "+0%"),
    "bright": ("+2%", "+2Hz", "+0%"),
    "neutral": ("+0%", "+0Hz", "+0%"),
}


_ROMAN_URDU = {
    "hai", "hain", "ho", "kya", "kyun", "ka", "ki", "ke", "mein", "main",
    "mujhe", "mujhay", "mera", "meri", "mere", "aap", "ap", "tum", "nahi",
    "nahin", "acha", "accha", "theek", "kar", "karo", "kr", "do", "batao",
    "chahiye", "wala", "wali", "aur", "se", "ko", "ye", "woh", "bohat", "bahut",
}

_LATIN_MARKERS: dict[str, set[str]] = {
    "fr": {"bonjour", "merci", "avec", "pour", "dans", "vous", "nous", "est", "une", "des", "pas"},
    "es": {"hola", "gracias", "como", "cómo", "para", "con", "una", "que", "por", "pero", "está", "muy"},
    "de": {"hallo", "danke", "und", "nicht", "ich", "ist", "mit", "für", "bitte", "das", "ein"},
    "it": {"ciao", "grazie", "come", "per", "con", "una", "che", "sono", "non", "molto"},
    "pt": {"olá", "ola", "obrigado", "obrigada", "para", "com", "uma", "que", "não", "nao", "muito"},
    "tr": {"merhaba", "teşekkür", "tesekkur", "için", "icin", "bir", "ve", "değil", "degil", "nasıl", "nasil"},
    "vi": {"xin", "chào", "chao", "cảm", "cam", "ơn", "ban", "bạn", "không", "khong", "và", "va"},
    "id": {"halo", "terima", "kasih", "dan", "untuk", "tidak", "saya", "kamu", "dengan", "ini"},
}


def normalize_language(value: str | None) -> str:
    raw = " ".join(str(value or "auto").strip().lower().replace("_", "-").split())
    if raw in ALIASES:
        return ALIASES[raw]
    base = raw.split("-", 1)[0]
    return base if base in LANGUAGES else "auto"


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", str(text or "").casefold(), flags=re.UNICODE)


def _count_range(text: str, start: int, end: int) -> int:
    return sum(1 for ch in text if start <= ord(ch) <= end)


def _ratio(count: int, total: int) -> float:
    return count / max(1, total)


def detect_language(text: str, *, preferred: str = "auto") -> tuple[str, float, str]:
    forced = normalize_language(preferred)
    if forced != "auto":
        return forced, 1.0, "preferred-language"

    value = str(text or "").strip()
    if not value:
        return "en", 0.25, "empty-default"

    letters = [ch for ch in value if ch.isalpha()]
    total = len(letters)

    # Highly distinctive scripts first.
    if any("HIRAGANA" in unicodedata.name(ch, "") or "KATAKANA" in unicodedata.name(ch, "") for ch in letters):
        return "ja", 0.99, "japanese-kana"
    hangul = _count_range(value, 0xAC00, 0xD7AF) + _count_range(value, 0x1100, 0x11FF)
    if hangul and _ratio(hangul, total) >= 0.25:
        return "ko", 0.99, "hangul-script"
    cjk = _count_range(value, 0x4E00, 0x9FFF)
    if cjk and _ratio(cjk, total) >= 0.25:
        return "zh", 0.96, "han-script"
    gurmukhi = _count_range(value, 0x0A00, 0x0A7F)
    if gurmukhi and _ratio(gurmukhi, total) >= 0.25:
        return "pa", 0.99, "gurmukhi-script"
    bengali = _count_range(value, 0x0980, 0x09FF)
    if bengali and _ratio(bengali, total) >= 0.25:
        return "bn", 0.99, "bengali-script"
    devanagari = _count_range(value, 0x0900, 0x097F)
    if devanagari and _ratio(devanagari, total) >= 0.25:
        return "hi", 0.96, "devanagari-script"
    thai = _count_range(value, 0x0E00, 0x0E7F)
    if thai and _ratio(thai, total) >= 0.25:
        return "th", 0.99, "thai-script"

    # Arabic-derived scripts: prioritize Urdu-specific letters, then Persian markers.
    arabic = _count_range(value, 0x0600, 0x06FF) + _count_range(value, 0x0750, 0x077F)
    if arabic and _ratio(arabic, total) >= 0.25:
        if re.search(r"[ٹڈڑںھہےےۓ]", value) or any(token in value for token in (" نہیں", " کیا", " مجھے", " آپ", " میں", " ہے")):
            return "ur", 0.98, "urdu-script"
        if re.search(r"[پچژگ]", value) or any(token in value for token in (" است", " برای", " شما", " می ")):
            return "fa", 0.91, "persian-script"
        return "ar", 0.91, "arabic-script"

    # Cyrillic: Ukrainian has distinctive letters; otherwise prefer Russian.
    cyr = _count_range(value, 0x0400, 0x04FF)
    if cyr and _ratio(cyr, total) >= 0.25:
        if re.search(r"[іїєґІЇЄҐ]", value):
            return "uk", 0.98, "ukrainian-cyrillic"
        return "ru", 0.93, "cyrillic-script"

    words = _words(value)
    wordset = set(words)
    if words:
        ur_score = len(wordset & _ROMAN_URDU)
        # Roman Urdu must show multiple signals to avoid hijacking short English text.
        if ur_score >= 3 or (ur_score >= 2 and len(words) <= 8):
            confidence = min(0.94, 0.58 + 0.07 * ur_score)
            return "ur", confidence, "roman-urdu-markers"

        best = ("en", 0)
        for code, markers in _LATIN_MARKERS.items():
            score = len(wordset & markers)
            if score > best[1]:
                best = (code, score)
        if best[1] >= 2:
            return best[0], min(0.93, 0.60 + 0.08 * best[1]), "latin-language-markers"

    # Diacritics are useful when sentences are short.
    lowered = value.casefold()
    if re.search(r"[ñ¿¡áéíóú]", lowered): return "es", 0.78, "spanish-diacritics"
    if re.search(r"[àâçéèêëîïôùûüœ]", lowered): return "fr", 0.76, "french-diacritics"
    if re.search(r"[äöüß]", lowered): return "de", 0.84, "german-diacritics"
    if re.search(r"[ãõç]", lowered): return "pt", 0.76, "portuguese-diacritics"
    if re.search(r"[ğışçöü]", lowered): return "tr", 0.84, "turkish-diacritics"
    if re.search(r"[ăâđêôơư]", lowered): return "vi", 0.86, "vietnamese-diacritics"

    return "en", 0.55, "latin-default"


def language_catalog() -> list[dict[str, Any]]:
    return [
        {
            "code": item.code,
            "locale": item.locale,
            "label": item.label,
            "female_voice": item.female_voice,
            "male_voice": item.male_voice,
            "direction": item.direction,
        }
        for item in LANGUAGES.values()
    ]


def resolve_voice(
    text: str,
    *,
    preferred_language: str | None = None,
    gender: str | None = None,
    mood: str | None = None,
    english_voice: str = "en-US-JennyNeural",
    english_alternate: str = "en-US-GuyNeural",
) -> VoiceSelection:
    preferred = preferred_language if preferred_language is not None else os.getenv("IRAS_LANGUAGE", "auto")
    code, confidence, reason = detect_language(text, preferred=preferred)
    spec = LANGUAGES.get(code, LANGUAGES["en"])

    wanted_gender = str(gender if gender is not None else os.getenv("IRAS_VOICE_GENDER", "female")).strip().lower()
    if wanted_gender not in {"female", "male"}:
        wanted_gender = "female"

    wanted_mood = str(mood if mood is not None else os.getenv("IRAS_VOICE_MOOD", "calm")).strip().lower()
    if wanted_mood not in MOODS:
        wanted_mood = "calm"
    rate, pitch, volume = MOODS[wanted_mood]

    female_voice = english_voice if code == "en" and english_voice else spec.female_voice
    male_voice = english_alternate if code == "en" and english_alternate else spec.male_voice
    voice = female_voice if wanted_gender == "female" else male_voice
    alternate = male_voice if wanted_gender == "female" else female_voice

    return VoiceSelection(
        language=code,
        locale=spec.locale,
        label=spec.label,
        voice=voice,
        alternate_voice=alternate,
        gender=wanted_gender,
        mood=wanted_mood,
        rate=rate,
        pitch=pitch,
        volume=volume,
        direction=spec.direction,
        confidence=float(confidence),
        reason=reason,
    )


def whisper_language_hint() -> str | None:
    value = normalize_language(os.getenv("IRAS_LANGUAGE", "auto"))
    return None if value == "auto" else value


def status() -> dict[str, Any]:
    return {
        "mode": normalize_language(os.getenv("IRAS_LANGUAGE", "auto")),
        "voice_mood": os.getenv("IRAS_VOICE_MOOD", "calm").strip().lower() or "calm",
        "voice_gender": os.getenv("IRAS_VOICE_GENDER", "female").strip().lower() or "female",
        "supported_languages": len(LANGUAGES),
        "catalog": language_catalog(),
        "roman_urdu_detection": True,
        "mixed_language_tts": "per-response dominant-language routing",
        "stt": "faster-whisper multilingual model with detected language metadata",
    }
