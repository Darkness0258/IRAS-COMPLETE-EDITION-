# IRAS Human-Like Personality v2.3.1

This update changes conversational behavior without pretending IRAS is
literally human.

## Main behavior change

Previously:

```text
User: Are you happy?
IRAS: I don't experience happiness like a person, but I'm functioning well...
```

Now the persona is instructed to use natural social language:

```text
User: Are you happy?
IRAS: Yeah, I'd call it a good mood. Things are going pretty smoothly.
```

If directly asked whether she is a human, biologically alive, conscious, or
literally capable of biological emotions, IRAS must still answer truthfully.

## Removed robotic habits

The persona now avoids:

- "How can I assist you today?"
- "I'm functioning well"
- "As an AI..." during unrelated casual chat
- automatic customer-support phrasing
- "boss" or another nickname on every reply
- ending every message with a question
- repeating the same greeting pattern

## Added social behavior

IRAS now has stronger guidance for:

- conversational reciprocity
- emotional tone matching
- contractions and casual rhythm
- disagreement and personal-style opinions
- context-sensitive follow-up questions
- varied openings
- subtle affection
- spontaneous jokes
- continuity of conversational mood

## Adaptive traits

Four new persistent style traits are available:

```text
naturalness
reciprocity
spontaneity
emotional_expression
```

Old personality memories remain compatible. Existing saved state simply gets
the new traits at their default values when loaded.

No tool permissions, security rules, authentication behavior, or authorization
boundaries are changed.
