# Fix for "tenant/user ... not found" (Render and Supabase)

## What the error means

Your Render log says:

```
FATAL:  (ENOTFOUND) tenant/user postgres.<your project> not found
```

Supabase has a front gate called the **pooler**. The gate answered, but it does not know your
project at the address in `DATABASE_URL`. The log shows the address
`aws-0-ap-southeast-2.pooler.supabase.com`.

This is **not** a password problem. A wrong password says `password authentication failed`.

It is one of three things, and only the Supabase page can tell which:

1. **The project is paused.** Free Supabase projects pause after about a week without use.
2. **The address is not the one Supabase shows for your project.** Pooler addresses look like
   `aws-0-<region>` or `aws-1-<region>`. Newer projects use `aws-1`, and the region must match.
3. **The project name in the user** (the part after `postgres.`) **is wrong,** or the project was deleted.

The server then crashed while starting, so Render restarted it again and again.

## Do this now

1. Open **supabase.com**, then your project. If it says **Project paused**, press **Restore project** and wait two minutes.
2. Press **Connect**, choose **Session pooler**, and copy the whole string. Do not edit it.
3. Open **Render**, then `iras-cloud`, then **Environment**, then `DATABASE_URL`. Paste it and save. Render redeploys.
4. When it is live, open `https://<your-service>.onrender.com/ready`. You want to see `"database": "postgres"`.

If the password has symbols, reset it in Supabase (Project Settings, Database, Reset database password) and use
letters and numbers only. Symbols like `@ # / : ? %` break the address unless they are percent-encoded.

### Check it on your PC before you deploy

PowerShell, in the IRAS folder (the tool never prints your password):

```powershell
$env:DATABASE_URL = "paste the string here"
python -m iras.memory.db_diagnose
python -m iras.memory.db_diagnose --all-regions    # if it says the project was not found
```

It tells you which host knows your project, or says the project is probably paused or deleted.

## Put the code fix in

The server should never die because of a wrong database address. This fix makes it explain the problem and
keep running on temporary storage until you correct `DATABASE_URL`.

**Option A, copy the files:** unzip this archive into your IRAS folder and let it replace the files.

**Option B, patch:** in the IRAS folder run `git apply database-fix.patch`

Then run `pytest tests/test_db_diagnose.py tests/test_render_supabase.py`, commit, and push. Render redeploys.

Files changed:

| File | What |
|---|---|
| `src/iras/memory/db_diagnose.py` | New. Explains database errors in plain words, hides passwords, checks the address, finds the right host. |
| `src/iras/cloud_bootstrap.py` | Tries the database once at start. Falls back to local storage, or stops if `IRAS_DATABASE_REQUIRED=true`. |
| `src/iras/cloud_api.py` | `/ready` now says `postgres`, `sqlite-local` or `sqlite-fallback`, and why. No host names or passwords. |
| `tests/test_db_diagnose.py` | 14 tests, including your real error message. |
| `docs/RENDER_SUPABASE_DEPLOY.md`, `render.yaml`, `.env.example` | A troubleshooting section and the new `IRAS_DATABASE_REQUIRED` setting. |

## What changes after the fix

- Wrong address: the log explains it in plain words and the server stays up. `/ready` shows `"database": "sqlite-fallback"`.
  The Command Center then shows **Local only** in the top bar.
- While it runs like that, memory is **not shared between devices** and is lost when Render restarts.
- If you prefer that it refuses to start, set `IRAS_DATABASE_REQUIRED=true`.
- Correct address: nothing changes.

Tested: the original code crashes in the same way as your log; the fixed code starts and answers `/health` and `/ready`.
The full suite on a clean copy went from 997 passed to 1024 passed (my 27 new tests added) with no other change.
I could not test against your real Supabase project, so step 1 to 3 above are on you.

## Please change your keys

The zip you sent contained your real `.env` file. I did not use the keys to reach any of your services, but the file
left your computer, so please treat these as exposed and replace them:

- `DATABASE_URL` (the database password): Supabase, Project Settings, Database, Reset database password
- `GEMINI_API_KEY`: Google AI Studio, create a new key and delete the old one
- `GROQ_API_KEY`: Groq console, create a new key and delete the old one
- `IRAS_API_TOKEN` and `IRAS_NODE_TOKEN`: run `generate-iras-token.ps1`, then update Render and your clients

Then update Render's environment. Good news: `.env` is in your `.gitignore` and was never committed (0 commits touched it).
Next time, leave `.env`, `.venv` and `.git` out of the zip.
