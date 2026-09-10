from __future__ import annotations

from dataclasses import dataclass


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


PROFILES: dict[str, VoiceProfile] = {
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
    'default': 'normal',
}


def normalize_profile(name: str | None) -> str:
    raw = ' '.join((name or 'anime_soft').strip().lower().replace('-', ' ').split())
    key = ALIASES.get(raw, raw.replace(' ', '_'))
    return key if key in PROFILES else 'anime_soft'


def get_profile(name: str | None) -> VoiceProfile:
    return PROFILES[normalize_profile(name)]


def profile_names() -> list[str]:
    return list(PROFILES)
