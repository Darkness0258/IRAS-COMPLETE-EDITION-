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
    "roman urdu": "roman-urdu", "roman-urdu": "roman-urdu", "roman_urdu": "roman-urdu", "romanurdu": "roman-urdu",
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
    "hai", "hain", "ho", "hoon", "hun", "tha", "thi", "the", "kya", "kia",
    "kyun", "ka", "ki", "ke", "mein", "main", "mujhe", "mujhay", "mera",
    "meri", "mere", "aap", "ap", "aapka", "aapki", "aapke", "tum", "tumhara",
    "nahi", "nahin", "haan", "han", "ji", "acha", "accha", "theek", "kar",
    "karo", "kr", "karna", "karni", "do", "batao", "sunao", "chahiye",
    "wala", "wali", "aur", "se", "ko", "ye", "yeh", "woh", "wo", "bohat",
    "bahut", "kaise", "kaisi", "kaisa", "kahan", "kab", "phir", "lekin",
    "magar", "saath", "sath", "chal", "raha", "rahi", "rahe", "lagta",
    "lagti", "hoga", "hogi", "yaar",
}

_LATIN_MARKERS: dict[str, set[str]] = {
    "en": {
        "hello", "hey", "how", "are", "you", "your", "what", "why", "where",
        "when", "please", "thanks", "thank", "good", "fine", "can", "could",
        "would", "should", "this", "that", "the", "is", "am", "we", "they",
        "my", "ready", "today", "tomorrow",
    },
    "fr": {
        "bonjour", "merci", "avec", "pour", "dans", "vous", "nous", "est",
        "une", "des", "pas", "je", "suis", "vais", "bien", "comment",
        "\u00e7a", "ca", "tr\u00e8s", "tres",
    },
    "es": {
        "hola", "gracias", "como", "c\u00f3mo", "para", "con", "una", "que",
        "por", "pero", "est\u00e1", "esta", "muy", "bien", "qu\u00e9", "tal",
        "usted", "ustedes", "soy", "estoy",
    },
    "de": {
        "hallo", "danke", "und", "nicht", "ich", "ist", "mit", "f\u00fcr",
        "fur", "bitte", "das", "ein", "wie", "geht", "dir", "mir", "gut",
    },
    "it": {
        "ciao", "grazie", "come", "per", "con", "una", "che", "sono",
        "non", "molto", "stai", "bene", "io", "tu", "oggi",
    },
    "pt": {
        "ol\u00e1", "ola", "obrigado", "obrigada", "para", "com", "uma", "que",
        "n\u00e3o", "nao", "muito", "bem", "como", "voc\u00ea", "voce", "estou",
    },
    "tr": {
        "merhaba", "te\u015fekk\u00fcr", "tesekkur", "i\u00e7in", "icin", "bir", "ve",
        "de\u011fil", "degil", "nas\u0131l", "nasil", "iyiyim", "sen", "siz",
    },
    "vi": {
        "xin", "ch\u00e0o", "chao", "c\u1ea3m", "cam", "\u01a1n", "ban", "b\u1ea1n",
        "kh\u00f4ng", "khong", "v\u00e0", "va", "t\u00f4i", "toi", "kh\u1ecfe", "khoe",
    },
    "id": {
        "halo", "terima", "kasih", "dan", "untuk", "tidak", "saya", "kamu",
        "dengan", "ini", "apa", "baik", "bagaimana",
    },
    "nl": {
        "hallo", "hoi", "dank", "dankjewel", "alsjeblieft", "hoe", "gaat",
        "het", "met", "jou", "goed", "ik", "ben", "niet",
    },
    "pl": {
        "cze\u015b\u0107", "czesc", "dzi\u0119kuj\u0119", "dziekuje", "prosz\u0119", "prosze",
        "jak", "si\u0119", "sie", "masz", "dobrze", "jestem", "nie", "tak",
    },
}

_STRONG_LATIN_MARKERS: dict[str, set[str]] = {
    "en": {"hello", "thanks", "please"},
    "fr": {"bonjour", "merci"},
    "es": {"hola", "gracias"},
    "de": {"hallo", "danke"},
    "it": {"ciao", "grazie"},
    "pt": {"ol\u00e1", "ola", "obrigado", "obrigada"},
    "tr": {"merhaba", "te\u015fekk\u00fcr", "tesekkur"},
    "vi": {"ch\u00e0o", "chao"},
    "id": {"terima", "kasih"},
    "nl": {"dankjewel", "alsjeblieft"},
    "pl": {"cze\u015b\u0107", "czesc", "dzi\u0119kuj\u0119", "dziekuje"},
}


def normalize_language(value: str | None) -> str:
    raw = " ".join(str(value or "roman-urdu").strip().lower().replace("_", "-").split())
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


def detect_language(text: str, *, preferred: str = "roman-urdu") -> tuple[str, float, str]:
    forced = normalize_language(preferred)
    roman_urdu_default = forced == "roman-urdu"
    if forced not in {"auto", "roman-urdu"}:
        return forced, 1.0, "preferred-language"

    value = str(text or "").strip()
    if not value:
        return ("ur", 0.80, "roman-urdu-default") if roman_urdu_default else ("en", 0.25, "empty-default")

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

        best_code = "en"
        best_score = 0
        for code, markers in _LATIN_MARKERS.items():
            score = len(wordset & markers)
            if score > best_score:
                best_code = code
                best_score = score

        if best_code != "en" and best_score >= 2 and best_score > ur_score:
            confidence = min(0.95, 0.62 + 0.07 * best_score)
            return best_code, confidence, "latin-language-markers"

        if ur_score >= 3 or (ur_score >= 2 and len(words) <= 10):
            confidence = min(0.96, 0.60 + 0.07 * ur_score)
            return "ur", confidence, "roman-urdu-markers"

        if best_score >= 2:
            confidence = min(0.95, 0.62 + 0.07 * best_score)
            return best_code, confidence, "latin-language-markers"

        for code, markers in _STRONG_LATIN_MARKERS.items():
            if wordset & markers:
                return code, 0.78, "strong-latin-marker"

    lowered = value.casefold()

    if re.search(r"[\u00f1\u00bf\u00a1]", lowered):
        return "es", 0.86, "spanish-distinctive-diacritics"
    if re.search(r"[\u0153\u00ea\u00e8\u00e0]", lowered):
        return "fr", 0.82, "french-distinctive-diacritics"
    if re.search(r"[\u00e4\u00f6\u00fc\u00df]", lowered):
        return "de", 0.88, "german-diacritics"
    if re.search(r"[\u00e3\u00f5]", lowered):
        return "pt", 0.88, "portuguese-distinctive-diacritics"
    if re.search(r"[\u011f\u0131\u015f]", lowered):
        return "tr", 0.88, "turkish-distinctive-diacritics"
    if re.search(r"[\u0103\u0111\u01a1\u01b0\u1ea1\u1ecf\u1edb\u1ef1]", lowered):
        return "vi", 0.90, "vietnamese-distinctive-diacritics"
    if re.search(r"[\u0105\u0107\u0119\u0142\u0144\u015b\u017a\u017c]", lowered):
        return "pl", 0.90, "polish-diacritics"

    if roman_urdu_default:
        return "en", 0.58, "latin-default-under-roman-urdu"
    return "en", 0.58, "latin-default"


def language_catalog() -> list[dict[str, Any]]:
    roman_voice = (
        os.getenv("IRAS_ROMAN_URDU_VOICE", "en-IN-NeerjaNeural").strip()
        or "en-IN-NeerjaNeural"
    )
    items = [
        {
            "code": item.code,
            "locale": item.locale,
            "label": item.label,
            "female_voice": item.female_voice,
            "direction": item.direction,
        }
        for item in LANGUAGES.values()
    ]
    items.insert(
        1,
        {
            "code": "roman-urdu",
            "locale": "en-IN",
            "label": "Roman Urdu (Latin)",
            "female_voice": roman_voice,
            "direction": "ltr",
        },
    )
    return items


def resolve_voice(
    text: str,
    *,
    preferred_language: str | None = None,
    gender: str | None = None,
    mood: str | None = None,
    english_voice: str = "en-US-JennyNeural",
    english_alternate: str = "en-US-GuyNeural",
) -> VoiceSelection:
    preferred = preferred_language if preferred_language is not None else os.getenv("IRAS_LANGUAGE", "roman-urdu")
    code, confidence, reason = detect_language(text, preferred=preferred)
    spec = LANGUAGES.get(code, LANGUAGES["en"])

    # IRAS has a fixed female voice identity. Keep the argument for backward
    # compatibility, but never route her to a male voice.
    wanted_gender = "female"

    wanted_mood = str(mood if mood is not None else os.getenv("IRAS_VOICE_MOOD", "calm")).strip().lower()
    if wanted_mood not in MOODS:
        wanted_mood = "calm"
    rate, pitch, volume = MOODS[wanted_mood]

    roman_latin = reason.startswith("roman-urdu")
    if roman_latin:
        roman_voice = (
            os.getenv("IRAS_ROMAN_URDU_VOICE", "en-IN-NeerjaNeural").strip()
            or "en-IN-NeerjaNeural"
        )
        voice = roman_voice
        alternate = english_voice or LANGUAGES["en"].female_voice
        selected_locale = "en-IN"
        selected_label = "Roman Urdu (Latin)"
    else:
        female_voice = english_voice if code == "en" and english_voice else spec.female_voice
        voice = female_voice
        alternate = female_voice
        selected_locale = spec.locale
        selected_label = spec.label

    return VoiceSelection(
        language=code,
        locale=selected_locale,
        label=selected_label,
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
    value = normalize_language(os.getenv("IRAS_LANGUAGE", "roman-urdu"))
    # Roman Urdu is a text/script preference. Keep multilingual Whisper
    # detection available so explicit language switches still work.
    if value in {"auto", "roman-urdu"}:
        return None
    return value


def status() -> dict[str, Any]:
    return {
        "mode": normalize_language(os.getenv("IRAS_LANGUAGE", "roman-urdu")),
        "voice_mood": os.getenv("IRAS_VOICE_MOOD", "calm").strip().lower() or "calm",
        "voice_gender": "female",
        "default_text_style": "roman-urdu",
        "default_speech_locale": "en-IN",
        "native_urdu_speech_locale": "ur-PK",
        "roman_urdu_voice": (
            os.getenv("IRAS_ROMAN_URDU_VOICE", "en-IN-NeerjaNeural").strip()
            or "en-IN-NeerjaNeural"
        ),
        "supported_languages": len(LANGUAGES),
        "catalog": language_catalog(),
        "roman_urdu_detection": True,
        "mixed_language_tts": "per-response dominant-language routing",
        "stt": "faster-whisper multilingual model with detected language metadata",
    }
