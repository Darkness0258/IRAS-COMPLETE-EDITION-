# IRAS Anime Voice — v1.2.0

The voice layer now changes both TTS prosody and the OpenRouter system persona.

Default: `anime_soft`

Commands:
- `voice styles`
- `voice style soft`
- `voice style genki`
- `voice style cool`
- `voice style normal`
- `voice test`

The Edge TTS backend receives profile-specific voice, rate, pitch, and volume values. Windows SAPI remains a fallback and receives the closest available rate setting.
