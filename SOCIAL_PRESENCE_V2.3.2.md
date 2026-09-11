# IRAS Social Presence Engine v2.3.2

This update fixes three visible conversational failures:

- robotic AI/feelings disclaimers during ordinary social chat;
- repeated vocative titles such as "boss";
- empty free-model streams becoming the literal reply "Done."

## Social guard

Casual turns such as:

```text
hello
how are you
are you happy
what are you thinking about
I'm bored
```

receive an additional high-priority social instruction.

The finished short social response also passes through a narrow style guard.
It can remove model-level phrases such as:

```text
As an AI...
I don't have feelings...
Not in the human sense...
I don't experience happiness...
I'm functioning well...
```

and repeated vocative titles:

```text
boss
sir
master
```

## Truthfulness

Literal identity/consciousness questions are excluded from the social rewrite:

```text
Are you actually human?
Are you conscious?
Do you really have biological feelings?
```

IRAS still answers those literally and truthfully.

The guard never invents a body, childhood, family, physical experiences, or a
human biography.

## Empty stream recovery

The previous agent used:

```python
if not final:
    final = "Done."
```

Now an empty stream retries once with the ordinary completion endpoint.
If that still has no usable text, IRAS says:

```text
I lost that response for a second. Try that again.
```

instead of "Done."

## Streaming

Normal factual and technical replies still stream token by token.

Very short social turns are buffered until their short answer is complete so a
bad model disclaimer can be removed before it appears on screen.

No APK or EXE rebuild is required because this behavior lives in the shared
Render backend.
