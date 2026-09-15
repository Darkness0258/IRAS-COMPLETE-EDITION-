# IRAS Cloud v2 architecture

```text
                         OpenRouter
                             ^
                             |
                       IRAS Cloud API
                       FastAPI / HTTPS
                             |
                    +--------+--------+
                    |                 |
              PostgreSQL          Web/PWA
             shared memory          client
                    ^
                    |
          +---------+----------+
          |                    |
    Windows IRAS.exe      Android IRAS.apk
      local TTS             native TTS
      local device          mic + speech
```

The public server intentionally does not expose shell, filesystem, process, or desktop-control tools.

Those capabilities belong to authorized local IRAS nodes. This prevents an internet-facing service from becoming a remote shell.

Future device-control architecture:

```text
IRAS Cloud -> authenticated job -> local IRAS node -> permission engine -> device tool
```

The cloud brain may request a local action, but the local node remains the enforcement point.
