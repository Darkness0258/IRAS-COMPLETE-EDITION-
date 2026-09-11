# IRAS Test Alignment Hotfix v2.3.4a

The v2.3.4 runtime behavior intentionally allows the user to request:

```text
boss
sir
master
```

However, two older tests from v2.3.2/v2.3.3 still required IRAS to remove
`boss`, while the newer title-preference tests require IRAS to preserve it.

Those requirements cannot both be correct at the same time.

This hotfix updates only the obsolete tests. It does not weaken or roll back
the runtime code.

Changed expectations:

```text
OLD:
"Hey, boss." -> "Hey."

NEW:
"Hey, boss." -> "Hey, boss."
```

The social-system test now verifies that titles are allowed when explicitly
requested, while still verifying that robotic AI-feelings disclaimers are
blocked in casual conversation.
