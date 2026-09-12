from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_type_text_uses_sendinput_not_clipboard():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "ui_control.py"
    ).read_text(encoding="utf-8")

    start = text.index("    def type_text(")
    end = text.index("    def click(", start)
    block = text[start:end]

    assert "SendInput" in block
    assert "KEYEVENTF_UNICODE" in block
    assert "_set_clipboard_text" not in block
    assert 'hotkey(["ctrl", "v"])' not in block
