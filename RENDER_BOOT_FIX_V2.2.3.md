# IRAS Render Boot Fix v2.2.3

## Symptom

Render shows:

```text
Application startup complete.
Uvicorn running on http://0.0.0.0:10000
Shutting down
...
Port scan timeout reached, no open ports detected.
```

## Cause

IRAS is launched with:

```text
python -m iras.cloud_api
```

but `main()` was also starting Uvicorn using:

```python
uvicorn.run("iras.cloud_api:app", ...)
```

That string makes Uvicorn import `iras.cloud_api` again.

Before the persistent Postgres optimization this duplicate import was mostly
wasteful. After the memory store began holding a live Supabase connection,
the duplicate import also created a second cloud runtime and a second live
database connection during boot.

## Fix

Uvicorn now receives the already-created app object:

```python
uvicorn.run(app, ...)
```

So cloud startup becomes:

```text
one Python module
-> one Settings object
-> one cloud runtime
-> one persistent Supabase connection
-> one FastAPI app
-> one Uvicorn server
```

The shutdown handler also closes the persistent memory connection cleanly.
