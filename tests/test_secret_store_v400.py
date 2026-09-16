from iras.security.secret_store import protect_secret, unprotect_secret, protection_backend


def test_secret_store_roundtrip_and_nonplaintext():
    value = "super-secret-validation-token"
    protected = protect_secret(value)
    assert protected != value
    assert unprotect_secret(protected) == value
    assert protection_backend() in {"windows-dpapi", "plain-test-fallback"}


def test_secret_store_accepts_legacy_plaintext_for_migration():
    assert unprotect_secret("legacy-token") == "legacy-token"
