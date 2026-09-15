from __future__ import annotations

import argparse
import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from iras import __version__
from iras.bootstrap import build_runtime
from iras.config import Settings
from iras.doctor import run as doctor_run
from iras.models import ApprovalRequest
from iras.voice.stt import Listener
from iras.voice.tts import Speaker
from iras.voice.profiles import PROFILES, normalize_profile
from iras.persona import build_system_prompt
from iras.vision.omniparser_runtime import OmniParserRuntimeManager


def _voice_intent(text: str):
    q = ' '.join(text.lower().strip().split())
    toggle = {'/voice', 'voice', 'toggle voice'}
    on = {'/voice on', 'voice on', 'turn voice on', 'enable voice', 'start voice', 'speak to me'}
    off = {'/voice off', 'voice off', 'turn voice off', 'disable voice', 'stop voice', 'stop speaking'}
    test = {'/voice test', 'voice test', 'test voice', 'test tts'}
    test_edge = {'/voice test edge', 'voice test edge', 'test edge voice'}
    test_windows = {'/voice test windows', 'voice test windows', 'test windows voice', 'voice test sapi'}
    if q in toggle:
        return 'toggle'
    if q in on:
        return 'on'
    if q in off:
        return 'off'
    if q in test_edge:
        return 'test_edge'
    if q in test_windows:
        return 'test_windows'
    if q in test:
        return 'test'
    return None



def _voice_profile_intent(text: str):
    q = ' '.join(text.lower().strip().split())
    if q in {'voice styles', 'voice profiles', 'list voice styles', 'list voice profiles'}:
        return ('list', None)
    prefixes = ('voice style ', 'voice profile ', 'anime voice ', 'anime ')
    for prefix in prefixes:
        if q.startswith(prefix):
            raw = q[len(prefix):].strip()
            if raw:
                return ('set', normalize_profile(raw))
    return None

def _listen_intent(text: str) -> bool:
    q = ' '.join(text.lower().strip().split())
    return q in {'listen', '/listen', 'mic', '/mic', 'microphone'}


def _vision_intent(text: str):
    q = ' '.join(text.lower().strip().split())
    if q in {'vision status', '/vision status', 'omniparser status', '/omniparser status'}:
        return 'status'
    if q in {'vision start', '/vision start', 'start omniparser', 'omniparser start', '/omniparser start'}:
        return 'start'
    return None


def main():
    ap = argparse.ArgumentParser(prog='iras')
    ap.add_argument('--doctor', action='store_true')
    ap.add_argument('--tools', action='store_true')
    ap.add_argument('--speak', action='store_true', help='force spoken replies on')
    ap.add_argument('--no-speak', action='store_true', help='force spoken replies off')
    ap.add_argument(
        '--voice-test', nargs='?', const='auto', choices=['auto', 'edge', 'windows'],
        help='play a TTS test using auto, edge, or native Windows speech'
    )
    args = ap.parse_args()
    c = Console()
    s = Settings.load()

    speaker = Speaker(s.tts_provider, s.voice, s.voice_profile)
    vision_runtime = OmniParserRuntimeManager()

    if args.voice_test is not None:
        try:
            backend = speaker.test(args.voice_test)
            c.print(f'[bold green]Playback command completed[/bold green] — backend: {backend}, {speaker.profile_summary()}')
            c.print('[dim]Important: this confirms the player returned successfully; only you can confirm whether audio was actually audible.[/dim]')
        except Exception as e:
            c.print(f'[bold red]Voice FAIL[/bold red] — {e}')
        return

    if args.doctor:
        t = Table('Check', 'Status', 'Detail')
        for n, ok, d in doctor_run(s):
            t.add_row(n, 'PASS' if ok else 'WARN', str(d))
        c.print(t)
        return

    def approve(req: ApprovalRequest):
        c.print(
            Panel(
                f"Tool: {req.tool_name}\nLevel: {req.permission.name}\nArguments:\n"
                f"{json.dumps(req.arguments, indent=2, default=str)[:4000]}",
                title='IRAS approval required',
            )
        )
        return c.input('[bold yellow]Approve this action? [y/N]: [/bold yellow]').strip().lower() in {'y', 'yes'}

    rt = build_runtime(s, approve)
    if args.tools:
        for x in rt.registry.describe():
            c.print(f"{x['name']}: {x['description']}")
        return

    listener = Listener(s.whisper_model, s.listen_seconds)
    c.print(
        Panel.fit(
            f'[bold]IRAS {__version__}[/bold]\n'
            f'Brain: {s.provider} / {s.model}\n'
            f'Voice profile: {speaker.profile.label} / {speaker.voice}\n'
            f'Vision: UIA + OmniParser ({"auto-start on demand" if vision_runtime.autostart_enabled() else "manual/external"})\n'
            'Commands: voice, voice test, voice styles, listen, vision status, vision start, personality status, /exit.'
        )
    )
    voice = s.voice_replies
    if args.speak:
        voice = True
    if args.no_speak:
        voice = False

    while True:
        try:
            q = c.input('[bold cyan]You > [/bold cyan]').strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not q:
            continue
        if q.lower() in {'/exit', 'exit', 'quit'}:
            break

        pq = ' '.join(q.lower().strip().split())

        vision_intent = _vision_intent(q)
        if vision_intent:
            if vision_intent == 'status':
                status = vision_runtime.status()
                c.print('[bold]OmniParser vision runtime[/bold]')
                for key in ('status', 'ready', 'autostart_enabled', 'local_endpoint', 'base_url', 'pid', 'started_by_iras', 'bridge_enabled', 'text_parse_url', 'log_path', 'reason', 'last_start_error'):
                    if key in status and status.get(key) is not None:
                        c.print(f'  {key}: {status.get(key)}')
            else:
                result = vision_runtime.ensure_ready(start=True)
                if result.ready:
                    c.print(f'[bold green]OmniParser ready[/bold green] — {result.status} at {result.base_url}')
                else:
                    c.print(f'[bold red]OmniParser unavailable[/bold red] — {result.status}: {result.reason}')
            continue

        if pq in {'personality', 'personality status', '/personality'}:
            state = rt.personality.status()
            c.print('[bold]Adaptive personality[/bold]')
            for name, value in state['traits'].items():
                c.print(f'  {name}: {int(round(value * 100))}/100')
            c.print('[dim]IRAS adjusts these gradually on her own from interaction style and model judgement.[/dim]')
            continue
        if pq in {'personality reset', '/personality reset'}:
            rt.personality.reset()
            c.print('[bold green]Adaptive personality reset to defaults.[/bold green]')
            continue

        profile_intent = _voice_profile_intent(q)
        if profile_intent:
            action, requested_profile = profile_intent
            if action == 'list':
                c.print('[bold]Voice profiles[/bold]')
                for key, profile in PROFILES.items():
                    marker = ' [green](active)[/green]' if key == speaker.profile_name else ''
                    c.print(f'  {key}: {profile.label} — {profile.voice}, rate {profile.rate}, pitch {profile.pitch}{marker}')
                continue

            speaker.set_profile(requested_profile)
            rt.agent.set_voice_profile(speaker.profile_name)
            c.print(f'[bold magenta]Voice style:[/bold magenta] {speaker.profile_summary()}')
            if voice:
                try:
                    speaker.speak(f'{speaker.profile.label} mode activated.')
                except Exception as e:
                    c.print(f'[bold red]Voice unavailable:[/bold red] {e}')
            continue

        intent = _voice_intent(q)
        if intent:
            if intent in {'test', 'test_edge', 'test_windows'}:
                try:
                    requested = 'edge' if intent == 'test_edge' else ('windows' if intent == 'test_windows' else 'auto')
                    backend = speaker.test(requested)
                    c.print(f'[bold green]Playback command completed[/bold green] — backend: {backend}, {speaker.profile_summary()}')
                    c.print('[dim]If you heard nothing, try `voice test windows` to isolate Windows audio from MPV.[/dim]')
                except Exception as e:
                    c.print(f'[bold red]Voice FAIL[/bold red] — {e}')
                continue

            old = voice
            if intent == 'toggle':
                voice = not voice
            elif intent == 'on':
                voice = True
            else:
                voice = False
            msg = f'Voice: {"on" if voice else "off"}'
            c.print(msg)
            if voice and not old:
                try:
                    backend = speaker.speak('Voice enabled.')
                    c.print(f'[dim]TTS backend: {backend}[/dim]')
                except Exception as e:
                    c.print(f'[bold red]Voice unavailable:[/bold red] {e}')
            continue

        if _listen_intent(q):
            c.print('[dim]Listening...[/dim]')
            try:
                heard = listener.listen_once()
            except Exception as e:
                c.print(f'[bold red]Microphone unavailable:[/bold red] {e}')
                continue
            if not heard:
                c.print('[yellow]I did not hear any speech.[/yellow]')
                continue
            q = heard
            c.print(f'[bold cyan]Heard >[/bold cyan] {q}')

        try:
            ans = rt.agent.handle(q)
        except Exception as e:
            ans = f'IRAS error: {type(e).__name__}: {e}'
        c.print(f'[bold magenta]IRAS >[/bold magenta] {ans}')
        if voice:
            try:
                speaker.speak(ans)
            except Exception as e:
                c.print(f'[bold red]Voice unavailable:[/bold red] {e}')

    try:
        rt.browser.close()
    except Exception:
        pass
