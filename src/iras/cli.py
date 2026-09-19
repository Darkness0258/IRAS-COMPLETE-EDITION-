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
from iras.remote_access import RemoteAccessPolicy
from iras.safety_runtime import EmergencyStop
from iras.master_control import MasterControl
from iras.coding_agent import build_coding_agent_graph
from iras.orchestration import format_orchestration_result


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
    if q in {'vision restart', '/vision restart', 'restart omniparser', 'omniparser restart', '/omniparser restart'}:
        return 'restart'
    if q in {'vision stop', '/vision stop', 'stop omniparser', 'omniparser stop', '/omniparser stop'}:
        return 'stop'
    return None


def main():
    ap = argparse.ArgumentParser(prog='iras')
    ap.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    ap.add_argument('--doctor', action='store_true')
    ap.add_argument('--tools', action='store_true')
    ap.add_argument('--speak', action='store_true', help='force spoken replies on')
    ap.add_argument('--no-speak', action='store_true', help='force spoken replies off')
    ap.add_argument(
        '--voice-test', nargs='?', const='auto', choices=['auto', 'edge', 'windows'],
        help='play a TTS test using auto, edge, or native Windows speech'
    )
    ap.add_argument('--remote-status', action='store_true', help='show the laptop-side remote-access safety policy')
    ap.add_argument('--remote-arm', choices=['read_only', 'control', 'full'], help='arm outbound remote Windows access locally')
    ap.add_argument('--remote-minutes', type=int, default=60, help='remote arm duration when not persistent')
    ap.add_argument('--remote-persistent', action='store_true', help='keep local remote access armed until explicitly disarmed')
    ap.add_argument('--remote-allow-power', action='store_true', help='allow restart/shutdown in full mode')
    ap.add_argument('--remote-allow-shell', action='store_true', help='reserve full-mode remote command execution (disabled unless explicitly enabled)')
    ap.add_argument('--remote-disarm', action='store_true', help='disarm laptop-side remote access')
    ap.add_argument('--emergency-stop', action='store_true', help='trip the controller-level emergency stop')
    ap.add_argument('--emergency-clear', action='store_true', help='clear the emergency stop locally')
    ap.add_argument('--master-status', action='store_true', help='show local owner Master Control status')
    ap.add_argument('--master-enable', nargs='?', const=30, type=int, metavar='MINUTES', help='enable local Master Control for a bounded number of minutes (default 30)')
    ap.add_argument('--master-persistent', action='store_true', help='keep Master Control active until explicitly disabled')
    ap.add_argument('--master-no-power', action='store_true', help='keep restart/shutdown disabled while Master Control is active')
    ap.add_argument('--master-no-shell', action='store_true', help='keep remote command execution disabled while Master Control is active')
    ap.add_argument('--master-no-autonomy', action='store_true', help='keep background multi-agent workers read-only while Master Control is active')
    ap.add_argument('--master-disable', action='store_true', help='disable Master Control and restore the previous remote policy')
    ap.add_argument('--vision-status', action='store_true', help='show OmniParser managed-runtime status')
    ap.add_argument('--vision-start', action='store_true', help='start/attach to the managed OmniParser runtime')
    ap.add_argument('--vision-restart', action='store_true', help='restart the IRAS-managed OmniParser runtime')
    ap.add_argument('--vision-stop', action='store_true', help='stop the IRAS-managed OmniParser runtime')
    args = ap.parse_args()
    c = Console()
    s = Settings.load()

    speaker = Speaker(s.tts_provider, s.voice, s.voice_profile)
    vision_runtime = OmniParserRuntimeManager()
    remote_policy = RemoteAccessPolicy()
    emergency_stop = EmergencyStop()
    master_control = MasterControl(remote_policy=remote_policy, emergency_stop=emergency_stop)

    if args.master_status:
        c.print_json(data=master_control.status())
        return
    if args.master_disable:
        c.print_json(data=master_control.disable(source="cli"))
        return
    if args.master_enable is not None:
        c.print(Panel(
            "Master Control gives IRAS CRITICAL registered-tool authority for this PC, "
            "suppresses per-action approval prompts, and can arm shell/power Remote capabilities.\n\n"
            "Emergency stop, audit logging, configured filesystem roots, Remote authentication, "
            "and Windows/UAC boundaries remain enforced.",
            title="IRAS Master Control", border_style="red"
        ))
        phrase = c.input('[bold red]Type ENABLE MASTER CONTROL to continue: [/bold red]').strip()
        if phrase != "ENABLE MASTER CONTROL":
            c.print('[yellow]Master Control was not enabled.[/yellow]')
            return
        c.print_json(data=master_control.enable(
            minutes=args.master_enable,
            persistent=args.master_persistent,
            allow_power=not args.master_no_power,
            allow_shell=not args.master_no_shell,
            autonomous=not args.master_no_autonomy,
            source="cli",
        ))
        return

    if args.emergency_stop:
        remote_policy.disarm(kill_switch=True)
        c.print_json(data=emergency_stop.trip("cli"))
        return
    if args.emergency_clear:
        c.print_json(data=emergency_stop.clear())
        return
    if args.remote_status:
        c.print_json(data=remote_policy.status())
        return
    if args.remote_disarm:
        c.print_json(data=remote_policy.disarm(kill_switch=True))
        return
    if args.remote_arm:
        try:
            state = remote_policy.arm(
                args.remote_arm,
                minutes=args.remote_minutes,
                persistent=args.remote_persistent,
                allow_power=args.remote_allow_power,
                allow_shell=args.remote_allow_shell,
            )
        except Exception as exc:
            c.print(f'[bold red]Remote access configuration failed:[/bold red] {exc}')
            return
        c.print_json(data=state)
        return

    if args.vision_status:
        c.print_json(data=vision_runtime.status())
        return
    if args.vision_start:
        result = vision_runtime.ensure_ready(start=True)
        c.print_json(data=result.as_dict())
        raise SystemExit(0 if result.ready else 2)
    if args.vision_restart:
        result = vision_runtime.restart()
        c.print_json(data=result.as_dict())
        raise SystemExit(0 if result.ready else 2)
    if args.vision_stop:
        result = vision_runtime.stop()
        c.print_json(data=result.as_dict())
        raise SystemExit(0 if result.status == 'stopped' else 2)

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
        return c.input('[bold yellow]Approve this action? [y/N]: [/bold yellow]').strip().lower() in {'y', 'yes', 'yeah', 'yep', 'yup', 'ok', 'okay', 'approve', 'approved'}

    rt = build_runtime(s, approve)
    last_code_run_id = ""
    if args.tools:
        for x in rt.registry.describe():
            c.print(f"{x['name']}: {x['description']}")
        return

    vision_runtime.start_supervisor(eager=True)
    if getattr(rt, "v5", None) is not None:
        rt.v5.start_services()

    listener = Listener(s.whisper_model, s.listen_seconds)
    c.print(
        Panel.fit(
            f'[bold]IRAS {__version__}[/bold]\n'
            f'Brain: {s.provider} / {s.model}\n'
            f'Voice profile: {speaker.profile.label} / {speaker.voice}\n'
            f'Vision: UIA + OmniParser ({"managed eager-start + watchdog" if vision_runtime.autostart_enabled() and vision_runtime.eager_start_enabled() else "manual/external"})\n'
            f'Remote Windows: {remote_policy.status().get("mode")} ({"armed" if remote_policy.status().get("enabled") else "disarmed"})\n'
            f'Emergency stop: {"ACTIVE" if emergency_stop.tripped() else "clear"}\n'
            f'Master Control: {"ON" if rt.master.status().get("enabled") else "off"}\n'
            'Commands: /code <goal>, /code status, master status/enable/disable, voice, listen, vision status/start/restart/stop, remote status, remote arm full, remote disarm, emergency stop, personality status, /exit.'
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

        if pq in {'/code', '/code status'}:
            manager = getattr(getattr(rt, "v5", None), "orchestration_manager", None)
            if not manager:
                c.print('[bold red]Coding Agent unavailable:[/bold red] local orchestration manager is not running.')
            elif not last_code_run_id:
                c.print('[yellow]No local Coding Agent run has been started yet. Use /code <goal>.[/yellow]')
            else:
                run = manager.get(last_code_run_id)
                c.print(format_orchestration_result(run) if run else 'The last Coding Agent run is no longer available.')
            continue
        if pq.startswith('/code '):
            objective = q[6:].strip()
            master_status = rt.master.status()
            manager = getattr(getattr(rt, "v5", None), "orchestration_manager", None)
            if not objective:
                c.print('[yellow]Usage: /code <coding objective>[/yellow]')
            elif not (master_status.get('enabled') and master_status.get('autonomous')):
                c.print('[yellow]Local Coding Agent execution requires Master Control with autonomous mode enabled. Enable Master Control, then retry.[/yellow]')
            elif not manager:
                c.print('[bold red]Coding Agent unavailable:[/bold red] local orchestration manager is not running.')
            else:
                try:
                    run = manager.submit_graph(
                        objective,
                        build_coding_agent_graph(objective),
                        context={"coding_agent": True, "coding_windows_control": True},
                        requester_device="local-cli",
                        add_coordinator=True,
                    )
                    last_code_run_id = str(run.get('run_id') or '')
                    c.print(f'[bold green]Coding Agent started[/bold green] · run {last_code_run_id}')
                    run = manager.wait(last_code_run_id, timeout=1800.0)
                    c.print(format_orchestration_result(run))
                except Exception as exc:
                    c.print(f'[bold red]Coding Agent failed:[/bold red] {type(exc).__name__}: {exc}')
            continue

        if pq in {'master status', '/master status', 'master'}:
            c.print_json(data=rt.master.status())
            continue
        if pq in {'master disable', '/master disable', 'master off', '/master off'}:
            c.print_json(data=rt.master.disable(source="interactive_cli"))
            continue
        if pq.startswith('master enable') or pq.startswith('/master enable') or pq in {'master on', '/master on'}:
            parts = pq.replace('/', '').split()
            minutes = 30
            for item in parts:
                if item.isdigit():
                    minutes = int(item)
                    break
            c.print(Panel(
                "This enables CRITICAL tool execution without per-action prompts for the bounded Master session. "
                "Type the exact phrase below to prove local owner intent.",
                title="Master Control", border_style="red"
            ))
            phrase = c.input('[bold red]Type ENABLE MASTER CONTROL: [/bold red]').strip()
            if phrase == 'ENABLE MASTER CONTROL':
                c.print_json(data=rt.master.enable(minutes=minutes, allow_power=True, allow_shell=True, autonomous=True, source='interactive_cli'))
            else:
                c.print('[yellow]Master Control was not enabled.[/yellow]')
            continue

        if pq in {'emergency stop', '/emergency stop', 'stop everything'}:
            remote_policy.disarm(kill_switch=True)
            c.print_json(data=emergency_stop.trip('interactive_cli'))
            continue
        if pq in {'emergency clear', '/emergency clear'}:
            c.print_json(data=emergency_stop.clear())
            continue
        if pq in {'remote status', '/remote status'}:
            c.print_json(data=remote_policy.status())
            continue
        if pq in {'remote disarm', '/remote disarm', 'remote stop', '/remote stop'}:
            c.print_json(data=remote_policy.disarm(kill_switch=True))
            continue
        if pq.startswith('remote arm') or pq.startswith('/remote arm'):
            parts = pq.replace('/', '').split()
            mode = parts[2] if len(parts) >= 3 else 'control'
            persistent = 'persistent' in parts or 'always' in parts
            allow_power = 'power' in parts
            allow_shell = 'shell' in parts
            try:
                c.print_json(data=remote_policy.arm(mode, persistent=persistent, allow_power=allow_power, allow_shell=allow_shell))
            except Exception as exc:
                c.print(f'[bold red]Remote access configuration failed:[/bold red] {exc}')
            continue

        vision_intent = _vision_intent(q)
        if vision_intent:
            if vision_intent == 'status':
                status = vision_runtime.status()
                c.print('[bold]OmniParser vision runtime[/bold]')
                for key in ('status', 'ready', 'autostart_enabled', 'local_endpoint', 'base_url', 'pid', 'started_by_iras', 'bridge_enabled', 'bridge_runtime', 'text_parse_url', 'text_prewarm_enabled', 'text_model_state', 'text_model_loaded', 'text_model_warmup_ms', 'full_model_state', 'full_model_loaded', 'full_model_warmup_ms', 'full_model_device', 'full_model_error', 'log_path', 'reason', 'text_model_error', 'last_start_error'):
                    if key in status and status.get(key) is not None:
                        c.print(f'  {key}: {status.get(key)}')
            elif vision_intent == 'start':
                result = vision_runtime.ensure_ready(start=True)
                if result.ready:
                    c.print(f'[bold green]OmniParser ready[/bold green] — {result.status} at {result.base_url}')
                else:
                    c.print(f'[bold red]OmniParser unavailable[/bold red] — {result.status}: {result.reason}')
            elif vision_intent == 'restart':
                result = vision_runtime.restart()
                if result.ready:
                    c.print(f'[bold green]OmniParser restarted[/bold green] — {result.status} at {result.base_url}')
                else:
                    c.print(f'[bold red]OmniParser restart failed[/bold red] — {result.status}: {result.reason}')
            else:
                result = vision_runtime.stop()
                if result.status == 'stopped':
                    c.print('[bold green]OmniParser stopped[/bold green]')
                else:
                    c.print(f'[bold yellow]OmniParser stop result[/bold yellow] — {result.status}: {result.reason}')
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
    try:
        if getattr(rt, "v5", None) is not None:
            rt.v5.stop_services()
            manager = getattr(rt.v5, "orchestration_manager", None)
            close = getattr(manager, "close", None)
            if callable(close):
                close()
    except Exception:
        pass
    vision_runtime.stop_supervisor()
