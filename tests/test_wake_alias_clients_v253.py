from pathlib import Path


ROOT = Path(
    __file__
).resolve().parents[1]


def test_web_supports_extra_wake_aliases():
    text = (
        ROOT
        / "clients"
        / "web"
        / "index.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "wakeAliases" in text
    assert "bestRecognitionTranscript" in text
    assert '"little girl"' in text
    assert '"cute"' in text


def test_android_supports_extra_wake_aliases():
    text = (
        ROOT
        / "clients"
        / "android"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "darkness"
        / "iras"
        / "MainActivity.java"
    ).read_text(
        encoding="utf-8"
    )

    assert "wakeAliases()" in text
    assert "wakePattern()" in text
    assert '"little girl"' in text
    assert '"cute"' in text
