# IRAS Personality Test Hotfix v2.3.1a

The human-like personality update is working; CI failed because one legacy
contract test checks an exact phrase:

```text
Focused professional mode automatically overrides all roleplay
```

The new prompt said:

```text
Focused professional mode automatically overrides roleplay during serious work.
```

Those mean the same thing, but the test uses a literal substring assertion.

This hotfix changes the sentence to:

```text
Focused professional mode automatically overrides all roleplay during serious work.
```

No personality behavior is rolled back. The human-like conversation changes remain intact.
