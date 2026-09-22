from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "payload"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=check)


def backup_file(root: Path, backup: Path, relative: str) -> None:
    src = root / relative
    if src.exists():
        dst = backup / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def replace_once(path: Path, old: str, new: str, *, sentinel: str = "") -> bool:
    text = path.read_text(encoding="utf-8-sig")
    if sentinel and sentinel in text:
        return False
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Patch anchor mismatch in {path}: expected 1 occurrence, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def replace_all(path: Path, old: str, new: str, *, minimum: int = 1, sentinel: str = "") -> int:
    text = path.read_text(encoding="utf-8-sig")
    if sentinel and sentinel in text:
        return 0
    count = text.count(old)
    if count < minimum:
        raise RuntimeError(f"Patch anchor mismatch in {path}: expected at least {minimum}, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")
    return count


def patch_config(root: Path) -> None:
    path = root / "src/iras/config.py"
    text = path.read_text(encoding="utf-8-sig")
    if "IRAS_WHISPER_MODEL', 'base')" in text:
        return
    replace_once(
        path,
        "whisper_model=os.getenv('IRAS_WHISPER_MODEL', 'base.en'),",
        "whisper_model=os.getenv('IRAS_WHISPER_MODEL', 'base'),",
    )


def patch_stt(root: Path) -> None:
    path = root / "src/iras/voice/stt.py"
    replace_once(
        path,
        "import time\n\n\nclass Listener:",
        "import time\n\nfrom iras.voice.multilingual_voice import whisper_language_hint\n\n\nclass Listener:",
        sentinel="from iras.voice.multilingual_voice import whisper_language_hint",
    )
    replace_once(
        path,
        '''    def __init__(self, model: str = "base.en", seconds: int = 6):\n        self.model_name = model\n        self.seconds = seconds\n        self._model = None\n        self._listen_lock = threading.Lock()\n''',
        '''    def __init__(self, model: str = "base", seconds: int = 6):\n        self.model_name = "base" if str(model or "").strip().lower() == "base.en" else str(model or "base")\n        self.seconds = seconds\n        self._model = None\n        self._listen_lock = threading.Lock()\n        self.last_language = ""\n        self.last_language_probability = 0.0\n''',
        sentinel="self.last_language_probability",
    )
    replace_once(
        path,
        '''            segments, _ = model.transcribe(str(path), vad_filter=True)\n            return " ".join(\n                segment.text.strip()\n                for segment in segments\n            ).strip()\n''',
        '''            segments, info = model.transcribe(\n                str(path),\n                vad_filter=True,\n                language=whisper_language_hint(),\n            )\n            self.last_language = str(getattr(info, "language", "") or "")\n            try:\n                self.last_language_probability = float(\n                    getattr(info, "language_probability", 0.0) or 0.0\n                )\n            except (TypeError, ValueError):\n                self.last_language_probability = 0.0\n            return " ".join(\n                segment.text.strip()\n                for segment in segments\n            ).strip()\n''',
        sentinel="language=whisper_language_hint()",
    )


def patch_tts(root: Path) -> None:
    path = root / "src/iras/voice/tts.py"
    replace_once(
        path,
        "from iras.voice.profiles import get_profile, normalize_profile\n",
        "from iras.voice.profiles import get_profile, normalize_profile\nfrom iras.voice.multilingual_voice import resolve_voice\n",
        sentinel="from iras.voice.multilingual_voice import resolve_voice",
    )
    replace_once(
        path,
        '''        self._stop_event = threading.Event()\n        self._speaking = threading.Event()\n''',
        '''        self._stop_event = threading.Event()\n        self._speaking = threading.Event()\n        self.last_language = "en"\n        self.last_locale = "en-US"\n        self.last_voice = self.voice\n        self.alternate_voice = "en-US-GuyNeural"\n''',
        sentinel="self.last_locale =",
    )
    replace_once(
        path,
        '''        with self._speak_lock:\n            self._stop_event.clear()\n            self._speaking.set()\n            try:\n                errors: list[str] = []\n''',
        '''        with self._speak_lock:\n            self._stop_event.clear()\n            self._speaking.set()\n            selection = resolve_voice(\n                text,\n                english_voice=self.profile.voice,\n                english_alternate="en-US-GuyNeural",\n            )\n            self.voice = selection.voice\n            self.alternate_voice = selection.alternate_voice\n            self.rate = selection.rate\n            self.pitch = selection.pitch\n            self.volume = selection.volume\n            self.last_language = selection.language\n            self.last_locale = selection.locale\n            self.last_voice = selection.voice\n            try:\n                errors: list[str] = []\n''',
        sentinel="selection = resolve_voice(",
    )
    replace_once(
        path,
        '''            await edge_tts.Communicate(\n                text,\n                self.voice,\n                rate=self.rate,\n                volume=self.volume,\n                pitch=self.pitch,\n            ).save(str(path))\n''',
        '''            try:\n                await edge_tts.Communicate(\n                    text,\n                    self.voice,\n                    rate=self.rate,\n                    volume=self.volume,\n                    pitch=self.pitch,\n                ).save(str(path))\n            except Exception:\n                if not self.alternate_voice or self.alternate_voice == self.voice:\n                    raise\n                await edge_tts.Communicate(\n                    text,\n                    self.alternate_voice,\n                    rate=self.rate,\n                    volume=self.volume,\n                    pitch=self.pitch,\n                ).save(str(path))\n                self.voice = self.alternate_voice\n                self.last_voice = self.voice\n''',
        sentinel="if not self.alternate_voice or self.alternate_voice == self.voice",
    )


def patch_persona(root: Path) -> None:
    path = root / "src/iras/persona.py"
    anchor = "SPEAKING STYLE:\n"
    block = '''LANGUAGE BEHAVIOR:\n- Detect and mirror the language the user is currently using unless they explicitly request another language.\n- If the user switches language, follow the switch naturally without announcing a mode change.\n- Mixed-language conversation is allowed. For English + Roman Urdu, reply naturally in the same mixed style when that improves clarity.\n- Preserve code, file paths, API names, commands, identifiers, and exact technical strings instead of translating them.\n- Do not translate the user's words unnecessarily before answering.\n- Use the target language's natural script when the user uses that script; do not force romanization unless requested.\n\nSPEAKING STYLE:\n'''
    replace_once(path, anchor, block, sentinel="LANGUAGE BEHAVIOR:")


def patch_tools(root: Path) -> None:
    path = root / "src/iras/tools/v5.py"
    replace_once(
        path,
        "from iras.v5.skills import SkillManifest\n",
        '''from iras.v5.skills import SkillManifest\nfrom iras.voice.multilingual_voice import (\n    detect_language as detect_spoken_language,\n    language_catalog as spoken_language_catalog,\n    resolve_voice as resolve_spoken_voice,\n    status as multilingual_voice_status,\n)\n''',
        sentinel="multilingual_voice_status",
    )
    anchor = "    # Voice + visual fusion ------------------------------------------------------------------\n"
    block = '''    # RC9 multilingual language + voice -------------------------------------------------------\n    add(Tool("v5_language_status", "Show IRAS multilingual STT/TTS mode, calming voice preset and supported language catalog.", _schema(), lambda: multilingual_voice_status(), PermissionLevel.READ))\n    add(Tool("v5_language_catalog", "List supported languages/locales with the preferred female and male neural voices.", _schema(), lambda: spoken_language_catalog(), PermissionLevel.READ))\n    add(Tool("v5_language_detect", "Detect the dominant language of text using local script/marker heuristics without sending it to another service.", _schema({"text": {"type": "string", "minLength": 1, "maxLength": 50000}, "preferred": _str(40)}, ["text"]), lambda text, preferred="auto": {"language": detect_spoken_language(text, preferred=preferred)[0], "confidence": detect_spoken_language(text, preferred=preferred)[1], "reason": detect_spoken_language(text, preferred=preferred)[2]}, PermissionLevel.READ))\n    add(Tool("v5_voice_resolve", "Resolve the calming native neural voice IRAS would use for one text response.", _schema({"text": {"type": "string", "minLength": 1, "maxLength": 50000}, "preferred_language": _str(40), "gender": {"type": "string", "enum": ["female", "male"]}, "mood": {"type": "string", "enum": ["calm", "warm", "bright", "neutral"]}}, ["text"]), lambda text, preferred_language="auto", gender="female", mood="calm": resolve_spoken_voice(text, preferred_language=preferred_language, gender=gender, mood=mood).as_dict(), PermissionLevel.READ))\n\n    # Voice + visual fusion ------------------------------------------------------------------\n'''
    replace_once(path, anchor, block, sentinel='"v5_language_status"')


def patch_cloud_api(root: Path) -> None:
    path = root / "src/iras/cloud_api.py"
    replace_once(
        path,
        '''from iras.voice.profiles import (\n    get_profile,\n)\n''',
        '''from iras.voice.profiles import (\n    get_profile,\n)\nfrom iras.voice.multilingual_voice import (\n    language_catalog,\n    resolve_voice,\n    status as multilingual_voice_status,\n)\n''',
        sentinel="multilingual_voice_status",
    )
    replace_once(
        path,
        '''class TTSIn(BaseModel):\n    text: str = Field(\n        min_length=1,\n        max_length=6000,\n    )\n''',
        '''class TTSIn(BaseModel):\n    text: str = Field(\n        min_length=1,\n        max_length=6000,\n    )\n    language: str = Field(default="", max_length=40)\n    voice_gender: str = Field(default="", pattern="^(|female|male)$")\n    mood: str = Field(default="", pattern="^(|calm|warm|bright|neutral)$")\n''',
        sentinel="voice_gender: str",
    )
    route_anchor = '@app.post("/v1/tts")\n'
    routes = '''@app.get("/v1/voice/catalog")\ndef voice_catalog(authorization: str | None = Header(default=None)):\n    _authorized(authorization)\n    return {"status": multilingual_voice_status(), "voices": language_catalog()}\n\n\n@app.post("/v1/voice/resolve")\ndef voice_resolve(body: TTSIn, authorization: str | None = Header(default=None)):\n    _authorized(authorization)\n    profile = get_profile(settings.voice_profile)\n    return resolve_voice(\n        body.text,\n        preferred_language=body.language or None,\n        gender=body.voice_gender or None,\n        mood=body.mood or None,\n        english_voice=profile.voice,\n    ).as_dict()\n\n\n@app.post("/v1/tts")\n'''
    replace_once(path, route_anchor, routes, sentinel='@app.get("/v1/voice/catalog")')
    replace_once(
        path,
        '''    profile = get_profile(\n        settings.voice_profile\n    )\n\n    try:\n        communicate = (\n            edge_tts.Communicate(\n                clean_text,\n                profile.voice,\n                rate=profile.rate,\n                volume=profile.volume,\n                pitch=profile.pitch,\n            )\n        )\n''',
        '''    profile = get_profile(\n        settings.voice_profile\n    )\n    selection = resolve_voice(\n        clean_text,\n        preferred_language=body.language or None,\n        gender=body.voice_gender or None,\n        mood=body.mood or None,\n        english_voice=profile.voice,\n    )\n\n    try:\n        communicate = (\n            edge_tts.Communicate(\n                clean_text,\n                selection.voice,\n                rate=selection.rate,\n                volume=selection.volume,\n                pitch=selection.pitch,\n            )\n        )\n''',
        sentinel="selection = resolve_voice(",
    )
    replace_once(
        path,
        '''                "X-IRAS-Voice": (\n                    profile.voice\n                ),\n                (\n                    "X-IRAS-"\n                    "Voice-Profile"\n                ): (\n                    settings\n                    .voice_profile\n                ),\n''',
        '''                "X-IRAS-Voice": selection.voice,\n                "X-IRAS-Language": selection.language,\n                "X-IRAS-Locale": selection.locale,\n                "X-IRAS-Voice-Mood": selection.mood,\n                (\n                    "X-IRAS-"\n                    "Voice-Profile"\n                ): (\n                    settings\n                    .voice_profile\n                ),\n''',
        sentinel='"X-IRAS-Language"',
    )


def patch_web(root: Path) -> None:
    path = root / "clients/web/index.html"
    replace_once(
        path,
        '''  <label>Wake word</label>\n  <input id="wake" placeholder="IRAS">\n  <div class="row">\n''',
        '''  <label>Wake word</label>\n  <input id="wake" placeholder="IRAS">\n  <label>Speech language</label>\n  <select id="language">\n    <option value="auto">Auto / browser language</option>\n    <option value="ur-PK">Urdu (Pakistan)</option>\n    <option value="en-US">English (US)</option>\n    <option value="hi-IN">Hindi</option>\n    <option value="ar-SA">Arabic</option>\n    <option value="pa-IN">Punjabi</option>\n    <option value="fa-IR">Persian</option>\n    <option value="bn-IN">Bengali</option>\n    <option value="tr-TR">Turkish</option>\n    <option value="fr-FR">French</option>\n    <option value="es-ES">Spanish</option>\n    <option value="de-DE">German</option>\n    <option value="it-IT">Italian</option>\n    <option value="pt-BR">Portuguese</option>\n    <option value="ru-RU">Russian</option>\n    <option value="uk-UA">Ukrainian</option>\n    <option value="ja-JP">Japanese</option>\n    <option value="ko-KR">Korean</option>\n    <option value="zh-CN">Mandarin Chinese</option>\n    <option value="vi-VN">Vietnamese</option>\n  </select>\n  <label>Voice mood</label>\n  <select id="voiceMood"><option value="calm">Calm</option><option value="warm">Warm</option><option value="bright">Bright</option><option value="neutral">Neutral</option></select>\n  <label>Voice</label>\n  <select id="voiceGender"><option value="female">Calm female</option><option value="male">Calm male</option></select>\n  <div class="row">\n''',
        sentinel='id="voiceMood"',
    )
    replace_once(
        path,
        '''wake.value=local.wakeWord||"IRAS";\nhandsFree=!!local.handsFree;\n''',
        '''wake.value=local.wakeWord||"IRAS";\n$("#language").value=local.language||"auto";\n$("#voiceMood").value=local.voiceMood||"calm";\n$("#voiceGender").value=local.voiceGender||"female";\nhandsFree=!!local.handsFree;\n''',
        sentinel='$("#voiceMood").value=local.voiceMood',
    )
    replace_once(
        path,
        '''    wakeWord:(wake.value.trim()||"IRAS"),\n    handsFree\n''',
        '''    wakeWord:(wake.value.trim()||"IRAS"),\n    language:($("#language").value||"auto"),\n    voiceMood:($("#voiceMood").value||"calm"),\n    voiceGender:($("#voiceGender").value||"female"),\n    handsFree\n''',
        sentinel='voiceMood:($("#voiceMood").value',
    )
    replace_once(
        path,
        '''function wakeWord(){return (config().wakeWord||"IRAS").trim()}\n\nfunction wakeAliases(){\n''',
        '''function wakeWord(){return (config().wakeWord||"IRAS").trim()}\nfunction speechLocale(){\n  const selected=(config().language||"auto").trim();\n  return selected&&selected!=="auto"?selected:(navigator.language||"en-US");\n}\n\nfunction wakeAliases(){\n''',
        sentinel="function speechLocale()",
    )
    replace_all(path, 'r.lang="en-US";', 'r.lang=speechLocale();', minimum=2, sentinel='r.lang=speechLocale();')
    replace_once(
        path,
        '''    body:JSON.stringify({text})\n''',
        '''    body:JSON.stringify({\n      text,\n      language:(c.language||"auto")==="auto"?"":c.language,\n      mood:c.voiceMood||"calm",\n      voice_gender:c.voiceGender||"female"\n    })\n''',
        sentinel="voice_gender:c.voiceGender",
    )


def patch_android(root: Path) -> None:
    path = root / "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java"
    replace_once(
        path,
        '''    private String wakeWord() {\n        String value =\n            prefs.getString(\n                "wake_word",\n                "IRAS"\n            ).trim();\n\n        return value.isEmpty()\n            ? "IRAS"\n            : value;\n    }\n\n''',
        '''    private String wakeWord() {\n        String value =\n            prefs.getString(\n                "wake_word",\n                "IRAS"\n            ).trim();\n\n        return value.isEmpty()\n            ? "IRAS"\n            : value;\n    }\n\n    private String speechLanguage() {\n        String configured = prefs.getString("speech_language", "auto").trim();\n        if (configured.isEmpty() || configured.equalsIgnoreCase("auto")) {\n            String system = Locale.getDefault().toLanguageTag();\n            return system == null || system.trim().isEmpty() ? "en-US" : system;\n        }\n        return configured;\n    }\n\n''',
        sentinel="private String speechLanguage()",
    )
    replace_once(
        path,
        '''        EditText wake =\n            new EditText(this);\n\n        wake.setHint("IRAS");\n        wake.setText(\n            wakeWord()\n        );\n\n        box.addView(server);\n        box.addView(token);\n        box.addView(wake);\n''',
        '''        EditText wake =\n            new EditText(this);\n\n        wake.setHint("IRAS");\n        wake.setText(\n            wakeWord()\n        );\n\n        EditText language = new EditText(this);\n        language.setHint("Speech language: auto, ur-PK, en-US, hi-IN...");\n        language.setText(prefs.getString("speech_language", "auto"));\n\n        EditText voiceMood = new EditText(this);\n        voiceMood.setHint("Voice mood: calm / warm / bright / neutral");\n        voiceMood.setText(prefs.getString("voice_mood", "calm"));\n\n        EditText voiceGender = new EditText(this);\n        voiceGender.setHint("Voice: female / male");\n        voiceGender.setText(prefs.getString("voice_gender", "female"));\n\n        box.addView(server);\n        box.addView(token);\n        box.addView(wake);\n        box.addView(language);\n        box.addView(voiceMood);\n        box.addView(voiceGender);\n''',
        sentinel='language.setHint("Speech language:',
    )
    replace_once(
        path,
        '''                        .putString(\n                            "wake_word",\n                            wakeValue\n                        )\n                        .apply();\n''',
        '''                        .putString(\n                            "wake_word",\n                            wakeValue\n                        )\n                        .putString(\n                            "speech_language",\n                            language.getText().toString().trim().isEmpty() ? "auto" : language.getText().toString().trim()\n                        )\n                        .putString(\n                            "voice_mood",\n                            voiceMood.getText().toString().trim().isEmpty() ? "calm" : voiceMood.getText().toString().trim()\n                        )\n                        .putString(\n                            "voice_gender",\n                            voiceGender.getText().toString().trim().equalsIgnoreCase("male") ? "male" : "female"\n                        )\n                        .apply();\n''',
        sentinel='"speech_language",',
    )
    replace_once(
        path,
        '''        i.putExtra(\n            RecognizerIntent\n                .EXTRA_LANGUAGE,\n            "en-US"\n        );\n''',
        '''        i.putExtra(\n            RecognizerIntent\n                .EXTRA_LANGUAGE,\n            speechLanguage()\n        );\n''',
        sentinel="speechLanguage()\n        );",
    )
    replace_once(
        path,
        '''            body.put(\n                "text",\n                text\n            );\n''',
        '''            body.put(\n                "text",\n                text\n            );\n            String voiceLanguage = prefs.getString("speech_language", "auto").trim();\n            if (!voiceLanguage.isEmpty() && !voiceLanguage.equalsIgnoreCase("auto")) {\n                body.put("language", voiceLanguage);\n            }\n            body.put("mood", prefs.getString("voice_mood", "calm"));\n            body.put("voice_gender", prefs.getString("voice_gender", "female"));\n''',
        sentinel='body.put("voice_gender"',
    )


def patch_env_example(root: Path) -> None:
    path = root / ".env.example"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8-sig")
    if "IRAS_LANGUAGE=auto" not in text:
        replace_once(
            path,
            "IRAS_WHISPER_MODEL=base.en\n",
            "IRAS_WHISPER_MODEL=base\nIRAS_LANGUAGE=auto\nIRAS_VOICE_MOOD=calm\nIRAS_VOICE_GENDER=female\n",
        )
    elif "IRAS_WHISPER_MODEL=base.en" in text:
        path.write_text(text.replace("IRAS_WHISPER_MODEL=base.en", "IRAS_WHISPER_MODEL=base"), encoding="utf-8")


def write_files(root: Path) -> None:
    mapping = {
        "src/iras/voice/multilingual_voice.py": PAYLOAD / "multilingual_voice.py",
        "tests/test_v500_rc9_multilingual_voice.py": PAYLOAD / "test_v500_rc9_multilingual_voice.py",
        "docs/V5_0_RC9_MULTILINGUAL_VOICE.md": PAYLOAD / "V5_0_RC9_MULTILINGUAL_VOICE.md",
    }
    for relative, source in mapping.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply cumulative IRAS RC9 multilingual voice overlay")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo).expanduser().resolve()

    required = [
        root / "src/iras/voice/stt.py",
        root / "src/iras/voice/tts.py",
        root / "src/iras/cloud_api.py",
        root / "src/iras/tools/v5.py",
        root / "src/iras/v5/strengthening_core.py",
        root / "src/iras/v5/cognitive_core.py",
        root / "src/iras/v5/automation_engine.py",
    ]
    if not all(p.exists() for p in required):
        print("ERROR: RC9 requires cumulative RC6 + RC7 + RC8 first. Use apply-iras-rc9.ps1 from the package.", file=sys.stderr)
        return 2

    marker = root / "src/iras/voice/multilingual_voice.py"
    if marker.exists() and "X-IRAS-Language" in (root / "src/iras/cloud_api.py").read_text(encoding="utf-8-sig"):
        print("IRAS RC9 multilingual voice overlay is already applied.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = root / ".iras_rc9_backup" / stamp
    targets = (
        "src/iras/config.py",
        "src/iras/voice/stt.py",
        "src/iras/voice/tts.py",
        "src/iras/persona.py",
        "src/iras/tools/v5.py",
        "src/iras/cloud_api.py",
        "clients/web/index.html",
        "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java",
        ".env.example",
    )
    for relative in targets:
        backup_file(root, backup, relative)

    try:
        write_files(root)
        patch_config(root)
        patch_stt(root)
        patch_tts(root)
        patch_persona(root)
        patch_tools(root)
        patch_cloud_api(root)
        patch_web(root)
        patch_android(root)
        patch_env_example(root)
    except Exception as exc:
        print(f"ERROR: RC9 patch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"Backups are in: {backup}", file=sys.stderr)
        return 4

    compile_targets = [
        "src/iras/voice/multilingual_voice.py",
        "src/iras/voice/stt.py",
        "src/iras/voice/tts.py",
        "src/iras/config.py",
        "src/iras/persona.py",
        "src/iras/tools/v5.py",
        "src/iras/cloud_api.py",
        "tests/test_v500_rc9_multilingual_voice.py",
    ]
    result = run([sys.executable, "-m", "py_compile", *compile_targets], root, check=False)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        print(f"ERROR: RC9 Python syntax validation failed. Backups are in: {backup}", file=sys.stderr)
        return result.returncode or 5

    if args.test:
        targets = ["tests/test_v500_rc9_multilingual_voice.py"]
        for prior in (
            "tests/test_v500_rc8_strengthening.py",
            "tests/test_v500_rc7_cognitive_core.py",
            "tests/test_v500_rc6_automation_voice.py",
        ):
            if (root / prior).exists():
                targets.append(prior)
        result = run([sys.executable, "-m", "pytest", *targets, "-q"], root, check=False)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            print(f"ERROR: targeted RC6-RC9 tests failed. Backups are in: {backup}", file=sys.stderr)
            return result.returncode

    print("IRAS RC9 multilingual voice overlay applied successfully.")
    print(f"Backup: {backup}")
    print("Default language: auto | voice mood: calm | voice gender: female")
    print("Urdu Pakistan: ur-PK-UzmaNeural / ur-PK-AsadNeural")
    print("Next validation: .\\run-v500-validation.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
