# IRAS Cloud v2.1 — Render + Supabase

## Target stack

```text
Backend     = Render Free
Database    = Supabase Free PostgreSQL
AI          = OpenRouter
Web app     = served by the same Render service
Android     = native APK client
Windows     = native EXE client
Hosting     = $0/month while remaining within free-tier limits
```

## Architecture

```text
Android APK ─┐
Windows EXE ─┼──── HTTPS ───► Render / IRAS FastAPI
Browser PWA ─┘                         │
                                      ├──► OpenRouter
                                      │
                                      └──► Supabase PostgreSQL
                                           shared memory/personality
```

The OpenRouter key stays on Render only.

The mobile, Windows, and web clients use only:

- Render server URL
- IRAS access token

## 1. Create Supabase database

Create a Supabase project.

In Supabase, obtain the PostgreSQL connection string from the database connection settings.

Use the connection string that works for server-side PostgreSQL clients. It will normally contain:

```text
postgresql://...
```

If Supabase provides multiple connection methods, prefer the pooled/session-compatible server connection string for a hosted app.

Store the complete connection string as:

```text
DATABASE_URL
```

on Render.

Do not put the database password inside the APK or EXE.

## 2. Push IRAS to GitHub

Upload this project to a GitHub repository.

Important files:

```text
Dockerfile
render.yaml
src/iras/cloud_api.py
src/iras/cloud_bootstrap.py
clients/web/
```

Do not commit `.env`.

## 3. Deploy on Render

Create a new Render Web Service from the GitHub repository.

You can either:

- use `render.yaml`, or
- create the service manually and choose Docker

Use the Free plan.

Set these environment variables in Render:

```text
IRAS_PROVIDER=openrouter
IRAS_MODEL=openrouter/free
OPENROUTER_API_KEY=<your OpenRouter key>
IRAS_API_TOKEN=<long random secret>
DATABASE_URL=<your Supabase PostgreSQL connection string>
IRAS_ADAPTIVE_PERSONALITY=true
IRAS_VOICE_PROFILE=anime_soft
IRAS_CORS_ORIGINS=*
```

Do not add `PORT` manually unless Render specifically requires it. Render supplies a port environment variable to web services.

## 4. Test deployment

When Render finishes deployment, test:

```text
https://YOUR-RENDER-DOMAIN/health
```

Expected response contains:

```json
{
  "ok": true,
  "service": "IRAS Cloud",
  "version": "2.1.0",
  "provider": "openrouter"
}
```

Then open:

```text
https://YOUR-RENDER-DOMAIN/app/
```

Enter:

- Render server URL
- the same `IRAS_API_TOKEN`

## 5. Connect Windows and Android

Both clients use the same two values:

```text
Server URL = https://YOUR-RENDER-DOMAIN
Token      = IRAS_API_TOKEN
```

The OpenRouter key is never copied into the clients.

## 6. Free-tier behavior

Render Free services may sleep after inactivity. If IRAS has been idle, the first request can take longer while the service wakes.

Supabase stores the durable memory, so Render sleeping or restarting does not erase the shared IRAS memory/personality.

## Security

Never expose these:

```text
OPENROUTER_API_KEY
DATABASE_URL
Supabase database password
```

Only the IRAS access token is entered into your clients.

If the IRAS access token leaks, generate a new one and update Render + your devices.
