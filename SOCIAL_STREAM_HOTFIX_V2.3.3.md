# IRAS Social Stream Hotfix v2.3.3

Fixes the two CI failures introduced by v2.3.2.

## 1. Literal identity detection

The previous detector used fixed substrings and missed:

```text
are you actually human?
```

v2.3.3 uses regex matching so optional words such as `actually`, `really`, and
`literally` are handled.

## 2. Streaming contract

The previous social guard called `provider.complete()` for `hello`, while the
existing streaming test explicitly requires ordinary no-tool chat to stay on
`provider.stream_text()`.

v2.3.3 keeps every no-tool turn on the streaming API.

For short social questions that commonly trigger robotic disclaimers, IRAS
buffers the short streaming answer, cleans it, then sends it to the client.

Plain greetings remain immediate streaming.

No APK or EXE rebuild is required.
