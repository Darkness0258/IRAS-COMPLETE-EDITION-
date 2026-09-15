# IRAS v1.4.0 — Autonomous Personality Adaptation

IRAS now adapts her communication style by herself.

## What she learns

Only interaction-style preferences:

- warmth
- affection
- teasing
- playful mock-jealousy
- harmless prank tendency
- humor
- directness
- verbosity
- softness
- assertiveness
- formality
- emoji tendency
- maturity

## How it works

There are two adaptation paths.

### 1. Quiet local observer

Each user message is examined for communication-style signals. Changes are deliberately tiny.

Examples:

- consistently short messages -> shorter IRAS replies
- casual slang -> slightly less formal
- laughter -> slightly more humor
- "too long" -> much stronger concise-response correction
- "be serious" -> less teasing/pranking
- "too childish" -> stronger mature style

### 2. IRAS self-adaptation tool

The OpenRouter model has an internal `adapt_personality` tool.

When it sees meaningful evidence that another style suits the user better, IRAS may call that tool on her own, change a few traits, persist the change, then continue the conversation.

She should not call it every turn.

## Persistent memory

The current adaptive state is stored locally in:

`data/iras.db`

under the durable fact key:

`iras.personality.adaptive.v1`

It survives restarts.

## Inspection

Inside IRAS:

```text
personality status
```

This is optional; no manual tuning is required.

To return to the factory personality:

```text
personality reset
```

## Immutable core

The adaptive layer cannot change:

- tool permission levels
- approval requirements
- authentication
- secret handling
- authorization boundaries
- truthfulness requirements
- privacy/security constraints
- the rule that serious work overrides roleplay

Jealousy and prank behavior are hard-capped at low levels and cannot become controlling, manipulative, destructive, or deceptive.

## Goal

IRAS should gradually feel more like *your* IRAS without requiring configuration screens or personality sliders.
