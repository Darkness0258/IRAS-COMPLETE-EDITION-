# IRAS Latency Hotfix v2.2.1

Fixes the CI failures:

```text
AttributeError: 'FakeProvider' object has no attribute 'last_request_ms'
```

The fallback tests use a minimal fake provider that does not implement
latency telemetry fields.

The production provider now reads optional telemetry safely with `getattr`,
so:

- real providers still report latency
- test doubles do not need telemetry fields
- fallback behavior is unchanged
- latency optimization remains enabled
