from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from iras.voice.profiles import get_profile, normalize_profile
from iras.voice.multilingual_voice import resolve_voice
from iras.voice.humanize import speech_text

class TTSUnavailable(RuntimeError):
    pass

class Speaker:
    def __init__(
        self,
        provider: str = "edge",
        voice: str | None = None,
        profile: str = "anime_soft",
    ):
        self.provider = provider
        self.profile_name = normalize_profile(profile)
        self.profile = get_profile(self.profile_name)
        self.voice = (
            self.profile.voice
            if self.profile_name != "normal"
            else (voice or self.profile.voice)
        )
        self.rate = self.profile.rate
        self.pitch = self.profile.pitch
        self.volume = self.profile.volume
        self.last_backend: str | None = None
        self.last_error: str | None = None
        self._speak_lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._process = None
        self._stop_event = threading.Event()
        self._speaking = threading.Event()
        self.last_language = "en"
        self.last_locale = "en-US"
        self.last_voice = self.voice
        self.alternate_voice = "en-US-GuyNeural"

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def set_profile(self, name: str) -> str:
        self.profile_name = normalize_profile(name)
        self.profile = get_profile(self.profile_name)
        self.voice = self.profile.voice
        self.rate = self.profile.rate
        self.pitch = self.profile.pitch
        self.volume = self.profile.volume
        return self.profile_name

    def profile_summary(self) -> str:
        return (
            f"{self.profile.label} — {self.voice}, rate {self.rate}, "
            f"pitch {self.pitch}, volume {self.volume}"
        )

    def stop(self) -> None:
        self._stop_event.set()
        with self._process_lock:
            process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass

    def _run_process(self, args, *, input_text: str | None = None):
        process = subprocess.Popen(
            args,
            stdin=(subprocess.PIPE if input_text is not None else subprocess.DEVNULL),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with self._process_lock:
            self._process = process
        try:
            stdout, stderr = process.communicate(input=input_text)
            return process.returncode, (stderr or stdout or "").strip()
        finally:
            with self._process_lock:
                if self._process is process:
                    self._process = None

    def speak(self, text: str) -> str:
        text = speech_text(text)
        if not text:
            return "none"

        with self._speak_lock:
            self._stop_event.clear()
            self._speaking.set()
            selection = resolve_voice(
                text,
                english_voice=self.profile.voice,
                english_alternate="en-US-GuyNeural",
            )
            self.voice = selection.voice
            self.alternate_voice = selection.alternate_voice
            self.rate = selection.rate
            self.pitch = selection.pitch
            self.volume = selection.volume
            self.last_language = selection.language
            self.last_locale = selection.locale
            self.last_voice = selection.voice
            try:
                errors: list[str] = []

                if self.provider in {"windows", "sapi", "windows-sapi"}:
                    backend = self._windows(text)
                    self.last_backend = backend
                    self.last_error = None
                    return backend

                if self.provider == "edge":
                    try:
                        backend = self._run_edge_sync(text)
                        self.last_backend = backend
                        self.last_error = None
                        return backend
                    except Exception as exc:
                        if self._stop_event.is_set():
                            return "interrupted"
                        errors.append(
                            f"Edge TTS: {type(exc).__name__}: {exc}"
                        )

                if os.name == "nt":
                    try:
                        backend = self._windows(text)
                        self.last_backend = backend
                        self.last_error = None
                        return backend
                    except Exception as exc:
                        if self._stop_event.is_set():
                            return "interrupted"
                        errors.append(
                            f"Windows SAPI: {type(exc).__name__}: {exc}"
                        )

                self.last_backend = None
                self.last_error = (
                    " | ".join(errors)
                    or "No compatible TTS backend is available."
                )
                raise TTSUnavailable(self.last_error)
            finally:
                self._speaking.clear()

    def _run_edge_sync(self, text: str) -> str:
        """Run Edge TTS from synchronous callers even inside an active loop.

        ``asyncio.run(coro)`` raises when the current thread already owns an
        event loop, and creating the coroutine before that check also produces
        a misleading "was never awaited" RuntimeWarning. IRAS can be embedded
        in async hosts, so use a short worker thread in that case.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._edge(text))

        result: dict[str, object] = {}

        def runner() -> None:
            try:
                result["value"] = asyncio.run(self._edge(text))
            except BaseException as exc:  # propagate on the calling thread
                result["error"] = exc

        thread = threading.Thread(
            target=runner,
            name="iras-edge-tts",
            daemon=True,
        )
        thread.start()
        thread.join()

        error = result.get("error")
        if isinstance(error, BaseException):
            raise error

        return str(result.get("value") or "edge+mpv")

    async def _edge(self, text: str) -> str:
        import edge_tts
        fd, raw_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        path = Path(raw_path)
        try:
            try:
                await edge_tts.Communicate(
                    text,
                    self.voice,
                    rate=self.rate,
                    volume=self.volume,
                    pitch=self.pitch,
                ).save(str(path))
            except Exception:
                if not self.alternate_voice or self.alternate_voice == self.voice:
                    raise
                await edge_tts.Communicate(
                    text,
                    self.alternate_voice,
                    rate=self.rate,
                    volume=self.volume,
                    pitch=self.pitch,
                ).save(str(path))
                self.voice = self.alternate_voice
                self.last_voice = self.voice

            if self._stop_event.is_set():
                return "interrupted"

            if not path.exists() or path.stat().st_size < 256:
                raise RuntimeError("Edge TTS produced an empty audio file.")

            mpv = self._find_mpv()
            if not mpv:
                raise RuntimeError("MPV was not found for Edge TTS playback.")

            code, detail = self._run_process(
                [
                    mpv,
                    "--no-config",
                    "--no-video",
                    "--ao=wasapi",
                    "--audio-device=auto",
                    "--volume=100",
                    "--mute=no",
                    "--really-quiet",
                    str(path),
                ]
            )

            if self._stop_event.is_set():
                return "interrupted"

            if code != 0:
                raise RuntimeError(
                    f"MPV exited with code {code}"
                    + (f": {detail[-800:]}" if detail else ".")
                )
            return "edge+mpv"
        finally:
            try:
                path.unlink()
            except OSError:
                pass

    @staticmethod
    def _find_mpv() -> str | None:
        found = shutil.which("mpv") or shutil.which("mpv.exe")
        if found:
            return found
        if os.name == "nt":
            candidates = [
                Path(r"C:\Program Files\MPV Player\mpv.exe"),
                Path(r"C:\Program Files\mpv\mpv.exe"),
                Path(os.environ.get("LOCALAPPDATA", ""))
                / "Programs" / "mpv" / "mpv.exe",
            ]
            for candidate in candidates:
                if str(candidate) and candidate.exists():
                    return str(candidate)
        return None

    def _windows(self, text: str) -> str:
        if os.name != "nt":
            raise RuntimeError("Windows SAPI is only available on Windows.")

        ps = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = [Console]::In.ReadToEnd()
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$female = $s.GetInstalledVoices() |
    Where-Object { $_.Enabled -and $_.VoiceInfo.Gender -eq 'Female' } |
    Select-Object -First 1
if ($female) { $s.SelectVoice($female.VoiceInfo.Name) }
$s.Volume = 100
$s.Rate = __RATE__
$s.Speak($text)
""".replace(
            "__RATE__",
            str(max(-10, min(10, self.profile.sapi_rate))),
        )

        code, detail = self._run_process(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                ps,
            ],
            input_text=text,
        )

        if self._stop_event.is_set():
            return "interrupted"

        if code != 0:
            raise RuntimeError(
                f"PowerShell speech exited with code {code}"
                + (f": {detail[-800:]}" if detail else ".")
            )
        return "windows-sapi"

    def test(self, backend: str = "auto") -> str:
        text = (
            f"IRAS {self.profile.label} voice is online. "
            "If you can hear this, audio playback is working."
        )
        backend = (backend or "auto").strip().lower()
        if backend in {"windows", "sapi", "windows-sapi"}:
            return self._windows(text)
        if backend == "edge":
            return asyncio.run(self._edge(text))
        return self.speak(text)
