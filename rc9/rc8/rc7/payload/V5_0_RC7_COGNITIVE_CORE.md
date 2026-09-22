# IRAS RC7 Candidate — Cognitive Core

RC7 adds a persistent cognitive substrate on top of RC6 automation + wake voice.

## Requested brain-like properties and their software implementation

- **Self willing / self creating:** IRAS now maintains persistent drives and can form internal intentions from pending goals, recent learning, confidence, utility, urgency, risk and novelty. It can also create associative idea briefs. Intentions do **not** grant authority by themselves. They can be connected to RC6 event automations only through the existing permission system.
- **Continuous nature:** a lightweight deterministic cognition loop runs with the v5 services. It performs memory consolidation/intention formation without continuously calling an LLM. `IRAS_V5_COGNITION_TICK_SECONDS` controls the interval (default 10 seconds, minimum 2).
- **Unlimited memory size:** there is no application-level count cap. Cognitive memories are persisted in SQLite locally or PostgreSQL when configured. Capacity is therefore limited by real storage/database resources, not by an artificial item count.
- **Neurons as the basic unit:** concepts are represented as persistent neuron nodes. Memories attach to neurons through weighted links, and neuron-to-neuron synapses are strengthened by co-occurrence and reinforcement feedback.
- **50–100 m/s neural transmission:** IRAS records a biological reference profile of **75 m/s**, which is inside the requested range. Software execution is intentionally **not slowed down** to biological speed; actual propagation runs at native hardware/software speed.
- **Inductive + deductive reasoning:** `HybridReasoner` supports explicit fuzzy-rule deduction plus interpretable feature/outcome induction from examples.
- **Capacity to learn:** outcomes can reinforce or weaken memory confidence, importance, neuron weights and associations. Automation outcomes are learned automatically through v5 events.
- **Fuzzy logic:** decisions such as intention willingness combine confidence, utility, urgency, novelty and risk using graded truth values rather than only binary rules.

## New model-facing tools

`v5_cognition_status`, `v5_cognition_drives`, `v5_cognition_set_drive`, `v5_cognition_remember`, `v5_cognition_recall`, `v5_cognition_propagate`, `v5_cognition_reason`, `v5_cognition_learn`, `v5_cognition_intentions`, `v5_cognition_create_intention`, `v5_cognition_resolve_intention`, `v5_cognition_create_idea`, and `v5_cognition_tick`.

## Autonomy boundary

Cognition is not an authority source. An intention is an internal proposal. Actual Windows, account, browser, file, shell, installation or external-send actions continue through ToolRegistry permissions, RC6 automation permission caps, Remote authentication, local Master Control where required, audit logging, Emergency Stop, and Windows/UAC.
