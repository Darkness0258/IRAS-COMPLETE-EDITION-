from pathlib import Path


def test_render_blueprint_exists():
    assert Path("render.yaml").exists()


def test_render_blueprint_uses_free_docker_service():
    text = Path("render.yaml").read_text(encoding="utf-8")
    assert "plan: free" in text
    assert "runtime: docker" in text
    assert "healthCheckPath: /health" in text


def test_render_blueprint_keeps_secrets_external():
    text = Path("render.yaml").read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY" in text
    assert "IRAS_API_TOKEN" in text
    assert "DATABASE_URL" in text
    assert "sync: false" in text


def test_supabase_database_is_generic_postgres():
    source = Path("src/iras/memory/postgres_store.py").read_text(encoding="utf-8")
    assert "psycopg.connect" in source
    assert "DATABASE_URL" in Path("RENDER_SUPABASE_DEPLOY.md").read_text(encoding="utf-8")
