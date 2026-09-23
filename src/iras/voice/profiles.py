from __future__ import annotations

from dataclasses import dataclass, replace
import os


@dataclass(frozen=True, slots=True)
class VoiceProfile:
    key: str
    label: str
    voice: str
    rate: str
    pitch: str
    volume: str
    sapi_rate: int
    persona: str
    fallback_voices: tuple[str, ...] = ()
    signature: str = "standard"


PROFILES: dict[str, VoiceProfile] = {
    'iras_human': VoiceProfile(
        key='iras_human',
        label='IRAS Human',
        voice='en-US-AvaMultilingualNeural',
        rate='-4%',
        pitch='+1Hz',
        volume='+0%',
        sapi_rate=0,
        persona=(
            'Use the signature IRAS personality: naturally feminine, warm, composed, intelligent, concise, and human. '
            'Use conversational rhythm and short natural sentences. Sound emotionally aware without pretending to be human, '
            'avoid robotic phrasing, exaggerated cuteness, baby talk, and repetitive filler. During technical or safety-critical '
            'work, become precise and focused while keeping the same calm identity.'
        ),
        fallback_voices=(
            'en-US-EmmaMultilingualNeural',
            'en-US-PhoebeMultilingualNeural',
            'en-US-JennyNeural',
        ),
        signature='human-feminine-multilingual',
    ),
    'anime_soft': VoiceProfile(
        key='anime_soft',
        label='Anime Young Adult',
        voice='en-US-JennyNeural',
        rate='-1%',
        pitch='+2Hz',
        volume='+0%',
        sapi_rate=0,
        persona=(
            'Use a warm young-adult anime-inspired personality: loving, confident, intelligent, concise, and natural. '
            'Keep sentences short and simple. Be gently teasing sometimes. Rarely use playful mock-jealousy or '
            'harmless verbal pranks in casual conversation, but never during serious work. Avoid childish speech, '
            'baby talk, clinginess, exaggerated cuteness, manipulation, or repetitive anime clichés.'
        ),
    ),
    'anime_genki': VoiceProfile(
        key='anime_genki',
        label='Anime Genki Adult',
        voice='en-US-JennyNeural',
        rate='+6%',
        pitch='+6Hz',
        volume='+1%',
        sapi_rate=1,
        persona=(
            'Use an energetic young-adult anime-inspired assistant personality. Sound lively and confident '
            'without becoming childish, squeaky, hyperactive, or unserious. During technical work, stay disciplined '
            'and factual. Use occasional lively reactions in casual conversation without exaggerated cuteness.'
        ),
    ),
    'anime_cool': VoiceProfile(
        key='anime_cool',
        label='Anime Cool',
        voice='en-US-AriaNeural',
        rate='-3%',
        pitch='+0Hz',
        volume='+0%',
        sapi_rate=0,
        persona=(
            'Use a cool, composed, anime-inspired assistant personality. Be calm, confident, slightly dry '
            'when joking, and highly focused during work. Avoid exaggerated emotion and keep answers clean.'
        ),
    ),
    'normal': VoiceProfile(
        key='normal',
        label='Normal',
        voice='en-US-AriaNeural',
        rate='+0%',
        pitch='+0Hz',
        volume='+0%',
        sapi_rate=0,
        persona='Use the standard IRAS personality: calm, confident, concise, capable, and natural.',
    ),
}

ALIASES = {
    'iras': 'iras_human',
    'human': 'iras_human',
    'human voice': 'iras_human',
    'natural': 'iras_human',
    'girl': 'iras_human',
    'female': 'iras_human',
    'iras human': 'iras_human',
    'iras_human': 'iras_human',
    'soft': 'anime_soft',
    'anime': 'anime_soft',
    'anime soft': 'anime_soft',
    'anime_soft': 'anime_soft',
    'genki': 'anime_genki',
    'energetic': 'anime_genki',
    'anime genki': 'anime_genki',
    'anime_genki': 'anime_genki',
    'cool': 'anime_cool',
    'anime cool': 'anime_cool',
    'anime_cool': 'anime_cool',
    'normal': 'normal',
    'default': 'iras_human',
}


def normalize_profile(name: str | None) -> str:
    raw = ' '.join((name or 'iras_human').strip().lower().replace('-', ' ').split())
    key = ALIASES.get(raw, raw.replace(' ', '_'))
    return key if key in PROFILES else 'iras_human'


def get_profile(name: str | None) -> VoiceProfile:
    profile = PROFILES[normalize_profile(name)]
    if profile.key != "iras_human":
        return profile

    custom_voice = os.getenv("IRAS_HUMAN_VOICE", "").strip()
    custom_fallbacks = tuple(
        item.strip()
        for item in os.getenv("IRAS_HUMAN_VOICE_FALLBACKS", "").split(",")
        if item.strip()
    )
    if not custom_voice and not custom_fallbacks:
        return profile
    return replace(
        profile,
        voice=custom_voice or profile.voice,
        fallback_voices=custom_fallbacks or profile.fallback_voices,
    )


def profile_names() -> list[str]:
    return list(PROFILES)


def profile_catalog() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for key in PROFILES:
        profile = get_profile(key)
        items.append(
            {
                "key": profile.key,
                "label": profile.label,
                "voice": profile.voice,
                "fallback_voices": list(profile.fallback_voices),
                "rate": profile.rate,
                "pitch": profile.pitch,
                "volume": profile.volume,
                "signature": profile.signature,
            }
        )
    return items
