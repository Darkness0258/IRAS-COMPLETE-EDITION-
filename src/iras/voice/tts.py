from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from iras.voice.profiles import get_profile, normalize_profile
from iras.voice.humanize import speech_text


class TTSUnavailable(RuntimeError):
    pass


class Speaker:
    def __init__(
        self,
        provider: str = 'edge',
        voice: str | None = None,
        profile: str = 'anime_soft',
    ):
        self.provider = provider
        self.profile_name = normalize_profile(profile)
        self.profile = get_profile(self.profile_name)
        # Non-normal profiles intentionally own the voice choice. For the normal
        # profile, a custom IRAS_VOICE value is still respected.
        self.voice = self.profile.voice if self.profile_name != 'normal' else (voice or self.profile.voice)
        self.rate = self.profile.rate
        self.pitch = self.profile.pitch
        self.volume = self.profile.volume
        self.last_backend: str | None = None
        self.last_error: str | None = None

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
            f'{self.profile.label} — {self.voice}, rate {self.rate}, '
            f'pitch {self.pitch}, volume {self.volume}'
        )

    def speak(self, text: str) -> str:
        # Display text may contain Markdown, emoji, URLs, code markers, and
        # other visual syntax. A human-like assistant should not read those
        # tokens aloud, so TTS gets a separate speech-friendly string.
        text = speech_text(text)
        if not text:
            return 'none'

        errors: list[str] = []

        if self.provider in {'windows', 'sapi', 'windows-sapi'}:
            backend = self._windows(text)
            self.last_backend = backend
            self.last_error = None
            return backend

        if self.provider == 'edge':
            try:
                backend = asyncio.run(self._edge(text))
                self.last_backend = backend
                self.last_error = None
                return backend
            except Exception as exc:
                errors.append(f'Edge TTS: {type(exc).__name__}: {exc}')

        if os.name == 'nt':
            try:
                backend = self._windows(text)
                self.last_backend = backend
                self.last_error = None
                return backend
            except Exception as exc:
                errors.append(f'Windows SAPI: {type(exc).__name__}: {exc}')

        self.last_backend = None
        self.last_error = ' | '.join(errors) or 'No compatible TTS backend is available.'
        raise TTSUnavailable(self.last_error)

    async def _edge(self, text: str) -> str:
        import edge_tts

        fd, raw_path = tempfile.mkstemp(suffix='.mp3')
        os.close(fd)
        path = Path(raw_path)
        try:
            await edge_tts.Communicate(
                text,
                self.voice,
                rate=self.rate,
                volume=self.volume,
                pitch=self.pitch,
            ).save(str(path))
            if not path.exists() or path.stat().st_size < 256:
                raise RuntimeError('Edge TTS produced an empty audio file.')

            mpv = self._find_mpv()
            if not mpv:
                raise RuntimeError('MPV was not found for Edge TTS playback.')

            completed = subprocess.run(
                [
                    mpv,
                    '--no-config',
                    '--no-video',
                    '--ao=wasapi',
                    '--audio-device=auto',
                    '--volume=100',
                    '--mute=no',
                    '--really-quiet',
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or '').strip()
                raise RuntimeError(
                    f'MPV exited with code {completed.returncode}'
                    + (f': {detail[-800:]}' if detail else '.')
                )
            return 'edge+mpv'
        finally:
            try:
                path.unlink()
            except OSError:
                pass

    @staticmethod
    def _find_mpv() -> str | None:
        found = shutil.which('mpv') or shutil.which('mpv.exe')
        if found:
            return found
        if os.name == 'nt':
            candidates = [
                Path(r'C:\Program Files\MPV Player\mpv.exe'),
                Path(r'C:\Program Files\mpv\mpv.exe'),
                Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'mpv' / 'mpv.exe',
            ]
            for candidate in candidates:
                if str(candidate) and candidate.exists():
                    return str(candidate)
        return None

    def _windows(self, text: str) -> str:
        if os.name != 'nt':
            raise RuntimeError('Windows SAPI is only available on Windows.')

        ps = r'''
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
'''.replace('__RATE__', str(max(-10, min(10, self.profile.sapi_rate))))
        completed = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps],
            input=text,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or '').strip()
            raise RuntimeError(
                f'PowerShell speech exited with code {completed.returncode}'
                + (f': {detail[-800:]}' if detail else '.')
            )
        return 'windows-sapi'

    def test(self, backend: str = 'auto') -> str:
        text = f'IRAS {self.profile.label} voice is online. If you can hear this, audio playback is working.'
        backend = (backend or 'auto').strip().lower()
        if backend in {'windows', 'sapi', 'windows-sapi'}:
            result = self._windows(text)
            self.last_backend = result
            self.last_error = None
            return result
        if backend == 'edge':
            result = asyncio.run(self._edge(text))
            self.last_backend = result
            self.last_error = None
            return result
        return self.speak(text)
