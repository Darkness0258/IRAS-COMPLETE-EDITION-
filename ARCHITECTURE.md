# IRAS architecture

```text
Voice / Desktop / CLI / API
            |
        Agent Core
            |
  Provider <-> Tool Registry
            |        |
          Memory   Permission Engine
                       |
                    Audit Log
                       |
    +----------+-------+---------+---------+
    |          |                 |         |
 Files      System/Shell       Browser     Git
    |          |                 |         |
 Local PC   Authorized OS    Public web   Repos

Remote machines run an authenticated IRAS Node with an independently capped permission policy.
```

## Trust model

1. LLM output is never executed directly.
2. Every capability is a named tool with a JSON schema.
3. Tool permission may depend on its arguments.
4. Elevated actions need a separate approval path.
5. Critical operations cannot be silently auto-approved.
6. External web/tool text is treated as untrusted data, not instructions.
7. Secrets are redacted from audit records.
8. Network fetch rejects private/link-local destinations.
