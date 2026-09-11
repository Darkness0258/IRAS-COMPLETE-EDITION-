# IRAS Wake Aliases v2.5.3

IRAS now accepts all previous pronunciation aliases plus:

```text
little girl
cute
```

Examples:

```text
"little girl"
→ wakes IRAS

"little girl, how are you?"
→ wakes IRAS and sends "how are you?"

"cute"
→ wakes IRAS

"cute tell me a joke"
→ wakes IRAS and sends "tell me a joke"
```

To reduce false wake-ups, aliases are matched at the beginning of a hands-free
utterance. For example:

```text
"that is cute"
```

does not wake IRAS.

This release is cumulative for the current v2.5.1 repository. It includes the
IRAS/Iris/Eris/eye-ris pronunciation aliases as well.

Release versions:

```text
Python / Windows: 2.5.3
Android versionName: 2.5.3
Android versionCode: 20503
```
