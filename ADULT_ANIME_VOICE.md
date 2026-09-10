# IRAS v1.2.1 — Young Adult Anime Voice

The default `anime_soft` profile now targets a young-adult female sound rather than a child-like voice.

## Changes

- Default voice: `en-US-JennyNeural`
- Rate: `-1%`
- Pitch: `+2Hz`
- Volume: `+0%`
- Persona explicitly avoids childish/babyish behavior
- `anime_genki` reduced from very high pitch/speed to adult energetic tuning
- `anime_cool` pitch returned to natural (`+0Hz`)
- Removed `cute` alias

The profile key remains `anime_soft`, so existing `.env` files continue to work unchanged.

## Commands

Inside IRAS:

```text
voice style soft
voice style genki
voice style cool
voice test
```

The default `soft` profile is now labeled **Anime Young Adult**.
