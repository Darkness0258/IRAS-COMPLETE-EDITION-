# IRAS v1.4.1 — Human-like Spoken Output

IRAS now separates **display text** from **speech text**.

The full assistant response remains visible on screen, but before TTS it is converted into natural speech.

## Removed from spoken audio

- emoji
- decorative symbols
- Markdown heading markers
- bold/italic/strike markers
- backticks
- bullet markers
- raw URLs
- Markdown link URLs
- table separators
- fenced code blocks

Markdown links keep only their readable label.

If a reply consists mainly of a code block, IRAS says:

> I put the code on screen.

instead of reading code punctuation aloud.

## Conversational behavior

The system prompt now tells IRAS to:

- prefer plain conversational text in casual chat
- avoid emoji and decorative symbols by default
- avoid stage directions such as `*smiles*` or `*pouts*`
- use Markdown only when useful for technical work

## Important

This changes only how responses are spoken and casually formatted. It does not remove code, URLs, symbols, or Markdown from the visible technical answer.
