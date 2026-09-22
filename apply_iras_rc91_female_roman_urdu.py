from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def replace_once(path: Path, old: str, new: str, *, allow_missing_if: str = "") -> bool:
    text = path.read_text(encoding="utf-8-sig")
    if allow_missing_if and allow_missing_if in text:
        return False
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Patch anchor mismatch in {path}: expected 1 occurrence, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def backup(root: Path, backup_root: Path, relative: str) -> None:
    src = root / relative
    if src.exists():
        dst = backup_root / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def patch_multilingual_voice(root: Path) -> None:
    path = root / "src/iras/voice/multilingual_voice.py"
    text = path.read_text(encoding="utf-8-sig")
    if '"default_text_style": "roman-urdu"' in text and 'wanted_gender = "female"' in text:
        return

    text = text.replace(
        '    "auto": "auto", "automatic": "auto",\n',
        '    "auto": "auto", "automatic": "auto",\n'
        '    "roman urdu": "roman-urdu", "roman-urdu": "roman-urdu", "roman_urdu": "roman-urdu", "romanurdu": "roman-urdu",\n',
        1,
    )
    text = text.replace(
        'raw = " ".join(str(value or "auto").strip().lower().replace("_", "-").split())',
        'raw = " ".join(str(value or "roman-urdu").strip().lower().replace("_", "-").split())',
        1,
    )
    text = text.replace(
        'def detect_language(text: str, *, preferred: str = "auto") -> tuple[str, float, str]:\n'
        '    forced = normalize_language(preferred)\n'
        '    if forced != "auto":\n'
        '        return forced, 1.0, "preferred-language"\n\n'
        '    value = str(text or "").strip()\n'
        '    if not value:\n'
        '        return "en", 0.25, "empty-default"\n',
        'def detect_language(text: str, *, preferred: str = "roman-urdu") -> tuple[str, float, str]:\n'
        '    forced = normalize_language(preferred)\n'
        '    roman_urdu_default = forced == "roman-urdu"\n'
        '    if forced not in {"auto", "roman-urdu"}:\n'
        '        return forced, 1.0, "preferred-language"\n\n'
        '    value = str(text or "").strip()\n'
        '    if not value:\n'
        '        return ("ur", 0.80, "roman-urdu-default") if roman_urdu_default else ("en", 0.25, "empty-default")\n',
        1,
    )
    text = text.replace(
        '    return "en", 0.55, "latin-default"\n',
        '    if roman_urdu_default:\n'
        '        return "ur", 0.72, "roman-urdu-default"\n'
        '    return "en", 0.55, "latin-default"\n',
        1,
    )
    text = text.replace('            "male_voice": item.male_voice,\n', '', 1)
    text = text.replace(
        'os.getenv("IRAS_LANGUAGE", "auto")',
        'os.getenv("IRAS_LANGUAGE", "roman-urdu")',
    )
    text = text.replace(
        '    wanted_gender = str(gender if gender is not None else os.getenv("IRAS_VOICE_GENDER", "female")).strip().lower()\n'
        '    if wanted_gender not in {"female", "male"}:\n'
        '        wanted_gender = "female"\n',
        '    # IRAS has a fixed female voice identity. Keep the argument for backward\n'
        '    # compatibility, but never route her to a male voice.\n'
        '    wanted_gender = "female"\n',
        1,
    )
    text = text.replace(
        '    female_voice = english_voice if code == "en" and english_voice else spec.female_voice\n'
        '    male_voice = english_alternate if code == "en" and english_alternate else spec.male_voice\n'
        '    voice = female_voice if wanted_gender == "female" else male_voice\n'
        '    alternate = male_voice if wanted_gender == "female" else female_voice\n',
        '    female_voice = english_voice if code == "en" and english_voice else spec.female_voice\n'
        '    voice = female_voice\n'
        '    # Never change IRAS to a male fallback voice. Existing backend fallback\n'
        '    # handles provider failure without changing her voice identity.\n'
        '    alternate = female_voice\n',
        1,
    )
    text = text.replace(
        'def whisper_language_hint() -> str | None:\n'
        '    value = normalize_language(os.getenv("IRAS_LANGUAGE", "roman-urdu"))\n'
        '    return None if value == "auto" else value\n',
        'def whisper_language_hint() -> str | None:\n'
        '    value = normalize_language(os.getenv("IRAS_LANGUAGE", "roman-urdu"))\n'
        '    # Roman Urdu is a text/script preference. Keep multilingual Whisper\n'
        '    # detection available so explicit language switches still work.\n'
        '    if value in {"auto", "roman-urdu"}:\n'
        '        return None\n'
        '    return value\n',
        1,
    )
    text = text.replace(
        '        "voice_gender": os.getenv("IRAS_VOICE_GENDER", "female").strip().lower() or "female",\n',
        '        "voice_gender": "female",\n'
        '        "default_text_style": "roman-urdu",\n'
        '        "default_speech_locale": "ur-PK",\n',
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_persona(root: Path) -> None:
    path = root / "src/iras/persona.py"
    text = path.read_text(encoding="utf-8-sig")
    old = (
        "LANGUAGE BEHAVIOR:\n"
        "- Detect and mirror the language the user is currently using unless they explicitly request another language.\n"
        "- If the user switches language, follow the switch naturally without announcing a mode change.\n"
        "- Mixed-language conversation is allowed. For English + Roman Urdu, reply naturally in the same mixed style when that improves clarity.\n"
    )
    new = (
        "LANGUAGE BEHAVIOR:\n"
        "- Your default conversation language is natural Roman Urdu written in Latin script.\n"
        "- Use Roman Urdu for greetings, short ambiguous messages, and ordinary conversation unless the user clearly requests or strongly uses another language.\n"
        "- If the user clearly switches to another supported language or explicitly asks for one, follow that switch naturally without announcing a mode change.\n"
        "- Mixed-language conversation is allowed. For English + Roman Urdu, reply naturally in the same mixed style when that improves clarity.\n"
    )
    if new not in text:
        if old not in text:
            raise RuntimeError("RC9 LANGUAGE BEHAVIOR block not found in persona.py")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def patch_tools(root: Path) -> None:
    path = root / "src/iras/tools/v5.py"
    text = path.read_text(encoding="utf-8-sig")
    text = text.replace(
        '"List supported languages/locales with the preferred female and male neural voices."',
        '"List supported languages/locales with IRAS\'s preferred female neural voices."',
    )
    text = text.replace('"enum": ["female", "male"]', '"enum": ["female"]')
    text = text.replace(
        'lambda text, preferred_language="auto", gender="female", mood="calm": resolve_spoken_voice',
        'lambda text, preferred_language="roman-urdu", gender="female", mood="calm": resolve_spoken_voice',
    )
    path.write_text(text, encoding="utf-8")


def patch_web(root: Path) -> None:
    path = root / "clients/web/index.html"
    text = path.read_text(encoding="utf-8-sig")
    text = text.replace(
        '<option value="auto">Auto / browser language</option>\n    <option value="ur-PK">Urdu (Pakistan)</option>',
        '<option value="roman-urdu">Roman Urdu (Default)</option>\n    <option value="auto">Auto detect</option>\n    <option value="ur-PK">Urdu script / Urdu (Pakistan)</option>',
        1,
    )
    text = text.replace('local.language||"auto"', 'local.language||"roman-urdu"')
    text = text.replace('$("#voiceGender").value=local.voiceGender||"female";\n', '')
    text = text.replace('language:($("#language").value||"auto")', 'language:($("#language").value||"roman-urdu")')
    text = text.replace('voiceGender:($("#voiceGender").value||"female")', 'voiceGender:"female"')
    text = text.replace(
        'const selected=(config().language||"auto").trim();\n  return selected&&selected!=="auto"?selected:(navigator.language||"en-US");',
        'const selected=(config().language||"roman-urdu").trim();\n  if(selected==="roman-urdu")return "ur-PK";\n  return selected&&selected!=="auto"?selected:(navigator.language||"ur-PK");',
        1,
    )
    text = text.replace(
        '<select id="voiceGender"><option value="female">Calm female</option><option value="male">Calm male</option></select>',
        '<div class="sub">IRAS female voice · fixed identity</div>',
        1,
    )
    text = text.replace(
        'language:(c.language||"auto")==="auto"?"":c.language,\n      mood:c.voiceMood||"calm",\n      voice_gender:c.voiceGender||"female"',
        'language:(c.language||"roman-urdu"),\n      mood:c.voiceMood||"calm",\n      voice_gender:"female"',
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_android(root: Path) -> None:
    path = root / "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java"
    text = path.read_text(encoding="utf-8-sig")
    text = text.replace('prefs.getString("speech_language", "auto").trim()', 'prefs.getString("speech_language", "roman-urdu").trim()')
    text = text.replace(
        'if (configured.isEmpty() || configured.equalsIgnoreCase("auto")) {\n            String system = Locale.getDefault().toLanguageTag();\n            return system == null || system.trim().isEmpty() ? "en-US" : system;',
        'if (configured.equalsIgnoreCase("roman-urdu")) return "ur-PK";\n        if (configured.isEmpty() || configured.equalsIgnoreCase("auto")) {\n            String system = Locale.getDefault().toLanguageTag();\n            return system == null || system.trim().isEmpty() ? "ur-PK" : system;',
        1,
    )
    text = text.replace('language.setHint("Speech language: auto, ur-PK, en-US, hi-IN...");', 'language.setHint("Speech language: roman-urdu, auto, ur-PK, en-US...");')
    text = text.replace('language.setText(prefs.getString("speech_language", "auto"));', 'language.setText(prefs.getString("speech_language", "roman-urdu"));')
    gender_block = (
        '        EditText voiceGender = new EditText(this);\n'
        '        voiceGender.setHint("Voice: female / male");\n'
        '        voiceGender.setText(prefs.getString("voice_gender", "female"));\n\n'
    )
    text = text.replace(gender_block, '', 1)
    text = text.replace('        box.addView(voiceGender);\n', '', 1)
    text = text.replace('voiceGender.getText().toString().trim().equalsIgnoreCase("male") ? "male" : "female"', '"female"')
    text = text.replace(
        'String voiceLanguage = prefs.getString("speech_language", "roman-urdu").trim();\n'
        '            if (!voiceLanguage.isEmpty() && !voiceLanguage.equalsIgnoreCase("auto")) {\n'
        '                body.put("language", voiceLanguage);\n'
        '            }\n'
        '            body.put("mood", prefs.getString("voice_mood", "calm"));\n'
        '            body.put("voice_gender", prefs.getString("voice_gender", "female"));',
        'String voiceLanguage = prefs.getString("speech_language", "roman-urdu").trim();\n'
        '            body.put("language", voiceLanguage.isEmpty() ? "roman-urdu" : voiceLanguage);\n'
        '            body.put("mood", prefs.getString("voice_mood", "calm"));\n'
        '            body.put("voice_gender", "female");',
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_env(root: Path) -> None:
    example = root / ".env.example"
    if example.exists():
        text = example.read_text(encoding="utf-8-sig")
        text = text.replace("IRAS_LANGUAGE=auto", "IRAS_LANGUAGE=roman-urdu")
        text = text.replace("IRAS_VOICE_GENDER=male", "IRAS_VOICE_GENDER=female")
        example.write_text(text, encoding="utf-8")

    actual = root / ".env"
    if actual.exists():
        text = actual.read_text(encoding="utf-8-sig")
        lines = []
        saw_lang = saw_gender = False
        for line in text.splitlines():
            if line.strip().startswith("IRAS_LANGUAGE="):
                lines.append("IRAS_LANGUAGE=roman-urdu")
                saw_lang = True
            elif line.strip().startswith("IRAS_VOICE_GENDER="):
                lines.append("IRAS_VOICE_GENDER=female")
                saw_gender = True
            else:
                lines.append(line)
        if not saw_lang:
            lines.append("IRAS_LANGUAGE=roman-urdu")
        if not saw_gender:
            lines.append("IRAS_VOICE_GENDER=female")
        actual.write_text("\n".join(lines) + "\n", encoding="utf-8")


def patch_tests_and_docs(root: Path) -> None:
    test = root / "tests/test_v500_rc9_multilingual_voice.py"
    text = test.read_text(encoding="utf-8-sig")
    old = '''def test_gender_alternate_and_english_profile_voice():\n    female = resolve_voice("Hello there", english_voice="en-US-AriaNeural", gender="female")\n    assert female.voice == "en-US-AriaNeural"\n    male = resolve_voice("Hello there", english_voice="en-US-AriaNeural", gender="male")\n    assert male.voice == "en-US-GuyNeural"\n    assert male.alternate_voice == "en-US-AriaNeural"\n'''
    new = '''def test_iras_voice_identity_is_always_female():\n    female = resolve_voice("Hello there", preferred_language="en", english_voice="en-US-AriaNeural", gender="female")\n    assert female.voice == "en-US-AriaNeural"\n    attempted_male = resolve_voice("Hello there", preferred_language="en", english_voice="en-US-AriaNeural", gender="male")\n    assert attempted_male.gender == "female"\n    assert attempted_male.voice == "en-US-AriaNeural"\n    assert attempted_male.alternate_voice == "en-US-AriaNeural"\n\n\ndef test_roman_urdu_is_default_fallback_but_clear_switches_still_work():\n    assert detect_language("hello there")[0] == "ur"\n    assert detect_language("bonjour merci pour votre aide")[0] == "fr"\n    assert detect_language("こんにちは、元気ですか")[0] == "ja"\n    default_voice = resolve_voice("hello there")\n    assert default_voice.locale == "ur-PK"\n    assert default_voice.voice == "ur-PK-UzmaNeural"\n'''
    if old in text:
        text = text.replace(old, new, 1)
    if 'normalize_language("Roman Urdu")' not in text:
        text = text.replace('    assert normalize_language("automatic") == "auto"\n', '    assert normalize_language("automatic") == "auto"\n    assert normalize_language("Roman Urdu") == "roman-urdu"\n')
    test.write_text(text, encoding="utf-8")

    doc = root / "docs/V5_0_RC9_MULTILINGUAL_VOICE.md"
    if doc.exists():
        text = doc.read_text(encoding="utf-8-sig")
        text = text.replace("IRAS_LANGUAGE=auto", "IRAS_LANGUAGE=roman-urdu")
        if "RC9.1 identity defaults" not in text:
            text += "\n## RC9.1 identity defaults\n\n- IRAS is always female across supported languages.\n- Default conversation text is Roman Urdu (Latin script).\n- Default speech locale is Urdu Pakistan (`ur-PK`) using `ur-PK-UzmaNeural`.\n- Strong or explicit language switches remain supported.\n"
        doc.write_text(text, encoding="utf-8")


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply IRAS RC9.1 female identity + Roman Urdu default overlay")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo).expanduser().resolve()

    required = [
        root / "src/iras/voice/multilingual_voice.py",
        root / "src/iras/persona.py",
        root / "src/iras/tools/v5.py",
        root / "clients/web/index.html",
        root / "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java",
    ]
    if not all(p.exists() for p in required):
        print("ERROR: RC9.1 requires RC9 first. Use apply-iras-rc91.ps1 from this package.", file=sys.stderr)
        return 2

    marker = root / "src/iras/voice/multilingual_voice.py"
    existing = marker.read_text(encoding="utf-8-sig")
    if '"default_text_style": "roman-urdu"' in existing and 'wanted_gender = "female"' in existing:
        print("IRAS RC9.1 female + Roman Urdu defaults are already applied.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = root / ".iras_rc91_backup" / stamp
    for rel in (
        "src/iras/voice/multilingual_voice.py", "src/iras/persona.py", "src/iras/tools/v5.py",
        "clients/web/index.html", "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java",
        ".env.example", ".env", "tests/test_v500_rc9_multilingual_voice.py", "docs/V5_0_RC9_MULTILINGUAL_VOICE.md",
    ):
        backup(root, backup_root, rel)

    try:
        patch_multilingual_voice(root)
        patch_persona(root)
        patch_tools(root)
        patch_web(root)
        patch_android(root)
        patch_env(root)
        patch_tests_and_docs(root)
    except Exception as exc:
        print(f"ERROR: RC9.1 patch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"Backups: {backup_root}", file=sys.stderr)
        return 4

    compile_targets = [
        "src/iras/voice/multilingual_voice.py", "src/iras/persona.py", "src/iras/tools/v5.py",
        "tests/test_v500_rc9_multilingual_voice.py",
    ]
    result = run([sys.executable, "-m", "py_compile", *compile_targets], root)
    if result.returncode:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        return result.returncode

    if args.test:
        result = run([sys.executable, "-m", "pytest", "tests/test_v500_rc9_multilingual_voice.py", "-q"], root)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode:
            return result.returncode

    print("IRAS RC9.1 applied successfully.")
    print("Identity: female")
    print("Default text language: Roman Urdu")
    print("Default speech locale: ur-PK")
    print("Default Urdu voice: ur-PK-UzmaNeural")
    print(f"Backup: {backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
