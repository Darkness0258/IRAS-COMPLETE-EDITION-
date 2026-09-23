from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog
from pathlib import Path

from iras.bootstrap import build_runtime
from iras.config import Settings
from iras.models import ApprovalRequest
from iras.security.redact import redact
from iras.voice.stt import Listener
from iras.voice.tts import Speaker
from iras.voice.approval import VoiceApprovalManager
from iras.coding_agent import build_coding_agent_graph
from iras.orchestration import format_orchestration_result


class App:
    """Polished local IRAS desktop shell using only the Python stdlib UI stack."""

    BG = "#070A11"
    PANEL = "#0D1320"
    PANEL_2 = "#111827"
    LINE = "#202A3D"
    TEXT = "#F4F7FF"
    MUTED = "#7F8CA6"
    PRIMARY = "#8B9CFF"
    CYAN = "#66E3FF"
    SUCCESS = "#5EE7A3"
    USER = "#202B4B"
    IRAS = "#121927"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("IRAS · Intelligence Workspace")
        self.root.geometry("1180x760")
        self.root.minsize(900, 620)
        self.root.configure(bg=self.BG)

        self.q: queue.Queue[tuple[str, str]] = queue.Queue()
        self.approval_q: queue.Queue[tuple[ApprovalRequest, threading.Event, dict]] = queue.Queue()
        self.settings = Settings.load()
        self.speaker = Speaker(self.settings.tts_provider, self.settings.voice, self.settings.voice_profile)
        self.listener = Listener(self.settings.whisper_model, self.settings.listen_seconds)
        self.voice_approver = VoiceApprovalManager(
            self.listener,
            self.speaker,
            enabled=self.settings.voice_approvals,
            critical_enabled=self.settings.voice_approval_critical,
            timeout_seconds=self.settings.voice_approval_timeout,
        )
        self.voice_on = tk.BooleanVar(value=self.settings.voice_replies)
        self.rt = build_runtime(self.settings, self.approve)
        self.master = self.rt.master
        self.last_code_run_id = ""
        self._pulse_on = True

        self._build_ui()
        self.append("IRAS", "Online. Your local intelligence workspace is ready.")
        self.root.after(100, self.poll)
        self.root.after(250, self._pulse_status)
        self.root.after(400, self._refresh_master_ui)
        self.root.bind("<Control-l>", lambda _e: self.entry.focus_set())
        self.root.bind("<Escape>", lambda _e: self.entry.focus_set())
        self._fade_in()

    def _font(self, size: int, weight: str = "normal"):
        return ("Segoe UI", size, weight)

    def _button(self, parent, text: str, command, *, primary: bool = False, width: int | None = None):
        bg = self.PRIMARY if primary else self.PANEL_2
        fg = "#08101C" if primary else "#D9E1F0"
        active = self.CYAN if primary else "#182237"
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active,
            activeforeground="#08101C" if primary else self.TEXT,
            borderwidth=0,
            relief="flat",
            font=self._font(10, "bold" if primary else "normal"),
            padx=14,
            pady=9,
            cursor="hand2",
            width=width,
            highlightthickness=0,
        )
        original = bg
        hover = "#A9B5FF" if primary else "#172035"
        button.bind("<Enter>", lambda _e: button.configure(bg=hover))
        button.bind("<Leave>", lambda _e: button.configure(bg=original))
        return button

    def _build_ui(self):
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        sidebar = tk.Frame(self.root, bg="#090E18", width=220, highlightbackground=self.LINE, highlightthickness=1)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        sidebar.grid_propagate(False)

        brand = tk.Frame(sidebar, bg="#090E18")
        brand.pack(fill="x", padx=18, pady=(18, 22))
        logo_path = Path(__file__).with_name("assets") / "iras-logo.png"
        try:
            image = tk.PhotoImage(file=str(logo_path))
            scale = max(1, max(image.width() // 70, image.height() // 70))
            self.logo_image = image.subsample(scale, scale)
            tk.Label(brand, image=self.logo_image, bg="#090E18", bd=0).pack(side="left")
            try:
                self.root.iconphoto(True, self.logo_image)
            except tk.TclError:
                pass
        except Exception:
            orb = tk.Canvas(brand, width=42, height=42, bg="#090E18", highlightthickness=0)
            orb.pack(side="left")
            orb.create_oval(4, 4, 38, 38, fill="#182443", outline="#3D4F80", width=1)
            orb.create_oval(13, 13, 29, 29, fill=self.CYAN, outline="")
            orb.create_oval(17, 17, 25, 25, fill="#0B1020", outline="")
        brand_copy = tk.Frame(brand, bg="#090E18")
        brand_copy.pack(side="left", padx=10)
        tk.Label(brand_copy, text="IRAS", bg="#090E18", fg=self.TEXT, font=self._font(15, "bold")).pack(anchor="w")
        tk.Label(
            brand_copy,
            text="INTELLIGENCE WORKSPACE",
            bg="#090E18",
            fg=self.MUTED,
            font=self._font(7, "bold"),
        ).pack(anchor="w", pady=(2, 0))

        tk.Label(sidebar, text="WORKSPACE", bg="#090E18", fg="#5F6C84", font=self._font(8, "bold")).pack(anchor="w", padx=20, pady=(0, 7))
        nav = tk.Frame(sidebar, bg="#090E18")
        nav.pack(fill="x", padx=12)
        nav_items = (
            ("  Chat", lambda: self.entry.focus_set()),
            ("  Voice input", self.listen),
            ("  System", lambda: self._set_status("System ready · local runtime healthy")),
        )
        for text, command in nav_items:
            btn = tk.Button(
                nav,
                text=text,
                command=command,
                anchor="w",
                bg="#121A2A" if text.strip() == "Chat" else "#090E18",
                fg=self.TEXT if text.strip() == "Chat" else "#AAB5CA",
                activebackground="#141E31",
                activeforeground=self.TEXT,
                borderwidth=0,
                relief="flat",
                padx=12,
                pady=10,
                font=self._font(10),
                cursor="hand2",
            )
            btn.pack(fill="x", pady=2)

        self.voice_button = tk.Button(
            nav,
            text=f"  Voice · {self.speaker.profile.label}",
            command=self._cycle_voice_profile,
            anchor="w",
            bg="#090E18",
            fg="#AAB5CA",
            activebackground="#141E31",
            activeforeground=self.TEXT,
            borderwidth=0,
            relief="flat",
            padx=12,
            pady=10,
            font=self._font(9, "bold"),
            cursor="hand2",
        )
        self.voice_button.pack(fill="x", pady=(7, 2))

        self.master_button = tk.Button(
            nav,
            text="  Master Control · OFF",
            command=self._toggle_master,
            anchor="w",
            bg="#090E18",
            fg="#AAB5CA",
            activebackground="#29131A",
            activeforeground="#FFD8DF",
            borderwidth=0,
            relief="flat",
            padx=12,
            pady=10,
            font=self._font(10, "bold"),
            cursor="hand2",
        )
        self.master_button.pack(fill="x", pady=(8, 2))

        info = tk.Frame(sidebar, bg="#0D1422", highlightbackground=self.LINE, highlightthickness=1)
        info.pack(side="bottom", fill="x", padx=12, pady=12)
        row = tk.Frame(info, bg="#0D1422")
        row.pack(fill="x", padx=12, pady=(12, 6))
        self.side_dot = tk.Canvas(row, width=10, height=10, bg="#0D1422", highlightthickness=0)
        self.side_dot.pack(side="left")
        self.side_dot_id = self.side_dot.create_oval(1, 1, 9, 9, fill=self.SUCCESS, outline="")
        tk.Label(row, text="  Local runtime", bg="#0D1422", fg="#BFDCCA", font=self._font(9)).pack(side="left")
        tk.Label(info, text="Voice · Vision · Device control", bg="#0D1422", fg=self.MUTED, font=self._font(8)).pack(anchor="w", padx=12, pady=(0, 5))
        self.voice_identity = tk.Label(
            info,
            text=f"{self.speaker.profile.label} · {self.speaker.voice.replace('en-US-', '').replace('Neural', '')}",
            bg="#0D1422",
            fg="#9EADFF",
            font=self._font(8, "bold"),
        )
        self.voice_identity.pack(anchor="w", padx=12, pady=(0, 12))

        main = tk.Frame(self.root, bg=self.PANEL, highlightbackground=self.LINE, highlightthickness=1)
        main.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        header = tk.Frame(main, bg=self.PANEL)
        header.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 14))
        header.grid_columnconfigure(0, weight=1)
        left = tk.Frame(header, bg=self.PANEL)
        left.grid(row=0, column=0, sticky="w")
        tk.Label(left, text="LOCAL INTELLIGENCE", bg=self.PANEL, fg="#70809B", font=self._font(8, "bold")).pack(anchor="w")
        tk.Label(left, text="Command Center", bg=self.PANEL, fg=self.TEXT, font=self._font(19, "bold")).pack(anchor="w", pady=(2, 0))
        tk.Label(left, text="Private device-first assistant with permissioned execution.", bg=self.PANEL, fg=self.MUTED, font=self._font(9)).pack(anchor="w", pady=(4, 0))

        header_actions = tk.Frame(header, bg=self.PANEL)
        header_actions.grid(row=0, column=1, sticky="e")
        voice_pill = tk.Frame(header_actions, bg="#11182A", highlightbackground="#33416A", highlightthickness=1)
        voice_pill.pack(side="left", padx=(0, 8))
        self.voice_orb = tk.Canvas(voice_pill, width=22, height=22, bg="#11182A", highlightthickness=0)
        self.voice_orb.pack(side="left", padx=(8, 0), pady=7)
        self.voice_orb_id = self.voice_orb.create_oval(5, 5, 17, 17, fill=self.PRIMARY, outline=self.CYAN)
        self.header_voice_label = tk.Label(voice_pill, text="IRAS HUMAN · READY", bg="#11182A", fg="#C7D0FF", font=self._font(8, "bold"))
        self.header_voice_label.pack(side="left", padx=(3, 9))

        status_pill = tk.Frame(header_actions, bg="#0D1B19", highlightbackground="#21453A", highlightthickness=1)
        status_pill.pack(side="left")
        self.header_dot = tk.Canvas(status_pill, width=14, height=14, bg="#0D1B19", highlightthickness=0)
        self.header_dot.pack(side="left", padx=(10, 0), pady=9)
        self.header_dot_id = self.header_dot.create_oval(3, 3, 11, 11, fill=self.SUCCESS, outline="")
        tk.Label(status_pill, text="IRAS ONLINE", bg="#0D1B19", fg="#B8E6D0", font=self._font(8, "bold")).pack(side="left", padx=(3, 10))

        chat_host = tk.Frame(main, bg="#0A0F19")
        chat_host.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        chat_host.grid_rowconfigure(0, weight=1)
        chat_host.grid_columnconfigure(0, weight=1)
        self.chat_canvas = tk.Canvas(chat_host, bg="#0A0F19", highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(chat_host, orient="vertical", command=self.chat_canvas.yview, bg=self.PANEL_2, troughcolor="#0A0F19", activebackground=self.PRIMARY)
        self.chat_canvas.configure(yscrollcommand=scrollbar.set)
        self.chat_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.chat_frame = tk.Frame(self.chat_canvas, bg="#0A0F19")
        self.chat_window = self.chat_canvas.create_window((0, 0), window=self.chat_frame, anchor="nw")
        self.chat_frame.bind("<Configure>", lambda _e: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all")))
        self.chat_canvas.bind("<Configure>", lambda e: self.chat_canvas.itemconfigure(self.chat_window, width=e.width))
        self.chat_canvas.bind_all("<MouseWheel>", lambda e: self.chat_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        composer_host = tk.Frame(main, bg=self.PANEL)
        composer_host.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        composer = tk.Frame(composer_host, bg="#111827", highlightbackground="#2A3650", highlightthickness=1)
        composer.pack(fill="x")
        mic = self._button(composer, "Mic", self.listen, width=5)
        mic.pack(side="left", padx=(8, 4), pady=8)
        self.entry = tk.Entry(
            composer,
            bg="#111827",
            fg=self.TEXT,
            insertbackground=self.TEXT,
            font=self._font(11),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=8, ipady=10)
        self.entry.bind("<Return>", lambda _e: self.send())
        send = self._button(composer, "Send", self.send, primary=True, width=6)
        send.pack(side="left", padx=(4, 8), pady=8)

        bottom = tk.Frame(composer_host, bg=self.PANEL)
        bottom.pack(fill="x", pady=(7, 0))
        self.status = tk.Label(bottom, text="Ready", bg=self.PANEL, fg=self.MUTED, font=self._font(8))
        self.status.pack(side="left")
        voice = tk.Checkbutton(
            bottom,
            text="Voice replies",
            variable=self.voice_on,
            bg=self.PANEL,
            fg="#B8C3D8",
            selectcolor=self.PANEL_2,
            activebackground=self.PANEL,
            activeforeground=self.TEXT,
            font=self._font(8),
            borderwidth=0,
            highlightthickness=0,
        )
        voice.pack(side="right")

    def _cycle_voice_profile(self):
        order = ["iras_human", "anime_soft", "anime_cool", "anime_genki", "normal"]
        try:
            index = order.index(self.speaker.profile_name)
        except ValueError:
            index = -1
        selected = order[(index + 1) % len(order)]
        self.speaker.set_profile(selected)
        try:
            self.rt.agent.set_voice_profile(selected)
        except Exception:
            pass
        self._refresh_voice_identity()
        self._set_status(f"Voice profile · {self.speaker.profile.label}")

    def _refresh_voice_identity(self):
        voice_short = self.speaker.profile.voice.replace("en-US-", "").replace("MultilingualNeural", "").replace("Neural", "")
        if hasattr(self, "voice_button"):
            self.voice_button.configure(text=f"  Voice · {self.speaker.profile.label}")
        if hasattr(self, "voice_identity"):
            self.voice_identity.configure(text=f"{self.speaker.profile.label} · {voice_short}")
        if hasattr(self, "header_voice_label"):
            self.header_voice_label.configure(text=f"{self.speaker.profile.label.upper()} · READY")

    def _toggle_master(self):
        state = self.master.status()
        if state.get("enabled"):
            if messagebox.askyesno(
                "Disable Master Control",
                "Disable Master Control now and restore the previous Remote policy?",
                parent=self.root,
            ):
                self.master.disable(source="desktop")
                self._set_status("Master Control disabled")
                self._refresh_master_ui()
            return

        phrase = simpledialog.askstring(
            "Enable Master Control",
            "Master Control grants IRAS CRITICAL registered-tool authority, shell/power Remote access, "
            "and autonomous execution for 30 minutes.\n\nEmergency stop, audit, configured filesystem roots, "
            "Remote authentication and Windows/UAC remain enforced.\n\nType ENABLE MASTER CONTROL to continue:",
            parent=self.root,
        )
        if phrase != "ENABLE MASTER CONTROL":
            self._set_status("Master Control was not enabled")
            return
        try:
            self.master.enable(
                minutes=30, allow_power=True, allow_shell=True, autonomous=True, source="desktop"
            )
            self._set_status("MASTER CONTROL ACTIVE · 30 minute owner session")
        except Exception as exc:
            messagebox.showerror("Master Control", str(exc), parent=self.root)
        self._refresh_master_ui()

    def _refresh_master_ui(self):
        if not hasattr(self, "master_button"):
            return
        state = self.master.status()
        if state.get("enabled"):
            remaining = state.get("remaining_seconds")
            if remaining is None:
                suffix = "PERSISTENT"
            else:
                minutes = max(1, int((int(remaining) + 59) // 60))
                suffix = f"{minutes}m"
            self.master_button.configure(
                text=f"  Master Control · ON · {suffix}",
                bg="#3A111B",
                fg="#FFD2DC",
            )
        else:
            self.master_button.configure(
                text="  Master Control · OFF",
                bg="#090E18",
                fg="#AAB5CA",
            )
        self.root.after(1000, self._refresh_master_ui)

    def _fade_in(self):
        try:
            self.root.attributes("-alpha", 0.0)
        except tk.TclError:
            return

        def step(alpha=0.0):
            alpha = min(1.0, alpha + 0.10)
            try:
                self.root.attributes("-alpha", alpha)
            except tk.TclError:
                return
            if alpha < 1.0:
                self.root.after(18, lambda: step(alpha))

        self.root.after(20, step)

    def _pulse_status(self):
        self._pulse_on = not self._pulse_on
        color = self.SUCCESS if self._pulse_on else "#2C7B5A"
        self.side_dot.itemconfigure(self.side_dot_id, fill=color)
        self.header_dot.itemconfigure(self.header_dot_id, fill=color)
        if hasattr(self, "voice_orb"):
            voice_color = self.CYAN if self._pulse_on else self.PRIMARY
            self.voice_orb.itemconfigure(self.voice_orb_id, fill=voice_color)
        self.root.after(950, self._pulse_status)

    def _set_status(self, text: str):
        self.status.configure(text=text)
        lowered = text.lower()
        voice_state = "READY"
        voice_color = "#C7D0FF"
        if any(word in lowered for word in ("error", "unavailable", "failed")):
            self.status.configure(fg="#FF8EA4")
            voice_state, voice_color = "ATTENTION", "#FF9AAD"
        elif "listening" in lowered:
            self.status.configure(fg="#8FE9FF")
            voice_state, voice_color = "LISTENING", "#8FE9FF"
        elif any(word in lowered for word in ("thinking", "working", "processing")):
            self.status.configure(fg="#A8B7FF")
            voice_state, voice_color = "THINKING", "#B4BEFF"
        elif "speaking" in lowered:
            self.status.configure(fg="#9FEAFF")
            voice_state, voice_color = "SPEAKING", "#9FEAFF"
        else:
            self.status.configure(fg=self.MUTED)
        if hasattr(self, "header_voice_label"):
            self.header_voice_label.configure(text=f"{self.speaker.profile.label.upper()} · {voice_state}", fg=voice_color)

    def append(self, who: str, text: str):
        mine = who.lower() == "you"
        row = tk.Frame(self.chat_frame, bg="#0A0F19")
        row.pack(fill="x", padx=22, pady=9)
        body = tk.Frame(row, bg="#0A0F19")
        body.pack(side="right" if mine else "left", anchor="e" if mine else "w")
        tk.Label(
            body,
            text="YOU" if mine else "IRAS",
            bg="#0A0F19",
            fg="#7E8CAF" if mine else self.PRIMARY,
            font=self._font(7, "bold"),
        ).pack(anchor="e" if mine else "w", padx=5, pady=(0, 4))
        bubble = tk.Label(
            body,
            text=text,
            justify="left",
            anchor="w",
            wraplength=650,
            bg=self.USER if mine else self.IRAS,
            fg=self.TEXT,
            font=self._font(10),
            padx=16,
            pady=12,
            borderwidth=1,
            relief="solid",
            highlightbackground="#34446C" if mine else self.LINE,
            highlightthickness=1,
        )
        bubble.pack(anchor="e" if mine else "w")
        self.root.after_idle(lambda: self.chat_canvas.yview_moveto(1.0))

    def approve(self, req: ApprovalRequest):
        if self.settings.voice_approvals:
            result = self.voice_approver.request(req)
            if result.resolved:
                return bool(result.approved)
        event = threading.Event()
        box: dict[str, bool] = {}
        self.approval_q.put((req, event, box))
        event.wait()
        return bool(box.get("v"))

    def _show_approval(self, req: ApprovalRequest, event: threading.Event, box: dict):
        win = tk.Toplevel(self.root)
        win.title("IRAS approval")
        win.configure(bg=self.PANEL)
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        win.geometry("520x360")

        tk.Label(win, text="Approval required", bg=self.PANEL, fg=self.TEXT, font=self._font(17, "bold")).pack(anchor="w", padx=24, pady=(24, 4))
        tk.Label(
            win,
            text=f"{req.tool_name} · {req.permission.name}",
            bg=self.PANEL,
            fg="#B3C0D8",
            font=self._font(9),
        ).pack(anchor="w", padx=24)
        args = tk.Text(win, height=10, wrap="word", bg="#090E18", fg="#C7D1E4", relief="flat", font=("Consolas", 9), padx=12, pady=10)
        args.pack(fill="both", expand=True, padx=24, pady=16)
        args.insert("1.0", json.dumps(redact(req.arguments), indent=2, default=str))
        args.configure(state="disabled")
        actions = tk.Frame(win, bg=self.PANEL)
        actions.pack(fill="x", padx=24, pady=(0, 22))

        def finish(value: bool):
            box["v"] = value
            event.set()
            win.grab_release()
            win.destroy()

        self._button(actions, "Deny", lambda: finish(False)).pack(side="right", padx=(8, 0))
        self._button(actions, "Approve", lambda: finish(True), primary=True).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", lambda: finish(False))

    def send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.append("You", text)
        self._set_status("IRAS is thinking…")
        threading.Thread(target=self.work, args=(text,), daemon=True).start()

    def work(self, text: str):
        try:
            raw = str(text or "").strip()
            lower = raw.lower()
            manager = getattr(getattr(self.rt, "v5", None), "orchestration_manager", None)
            if lower in {"/code", "/code status"}:
                if not manager:
                    ans = "Coding Agent is unavailable because the local orchestration manager is not running."
                elif not self.last_code_run_id:
                    ans = "No local Coding Agent run has been started yet. Use /code <goal>."
                else:
                    run = manager.get(self.last_code_run_id)
                    ans = format_orchestration_result(run) if run else "The last Coding Agent run is no longer available."
            elif lower.startswith("/code "):
                objective = raw[6:].strip()
                master_status = self.master.status()
                if not objective:
                    ans = "Usage: /code <coding objective>"
                elif not (master_status.get("enabled") and master_status.get("autonomous")):
                    ans = (
                        "Local Coding Agent execution requires Master Control with autonomous mode enabled. "
                        "Enable Master Control, then send the /code request again."
                    )
                elif not manager:
                    ans = "Coding Agent is unavailable because the local orchestration manager is not running."
                else:
                    run = manager.submit_graph(
                        objective,
                        build_coding_agent_graph(objective),
                        context={"coding_agent": True, "coding_windows_control": True},
                        requester_device="local-desktop",
                        add_coordinator=True,
                    )
                    self.last_code_run_id = str(run.get("run_id") or "")
                    run = manager.wait(self.last_code_run_id, timeout=1800.0)
                    ans = format_orchestration_result(run)
            else:
                ans = self.rt.agent.handle(text)
        except Exception as exc:
            ans = f"Error: {type(exc).__name__}: {exc}"
        self.q.put(("answer", ans))

    def listen(self):
        self._set_status(f"Listening for {self.settings.listen_seconds} seconds…")
        threading.Thread(target=self.listen_work, daemon=True).start()

    def listen_work(self):
        try:
            text = self.listener.listen_once()
            self.q.put(("heard", text))
        except Exception as exc:
            self.q.put(("answer", f"Voice input unavailable: {exc}"))

    def poll(self):
        try:
            while True:
                req, event, box = self.approval_q.get_nowait()
                self._show_approval(req, event, box)
        except queue.Empty:
            pass

        try:
            while True:
                kind, value = self.q.get_nowait()
                if kind == "heard":
                    self.append("You", value)
                    self._set_status("IRAS is thinking…")
                    threading.Thread(target=self.work, args=(value,), daemon=True).start()
                elif kind == "voice_state":
                    self._set_status("IRAS is speaking…" if value == "speaking" else "Ready")
                    continue
                else:
                    self.append("IRAS", value)
                    self._set_status("Ready")
                    if self.voice_on.get():
                        def speak_reply(reply=value):
                            self.q.put(("voice_state", "speaking"))
                            try:
                                self.speaker.speak(reply)
                            finally:
                                self.q.put(("voice_state", "ready"))
                        threading.Thread(target=speak_reply, daemon=True).start()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def run(self):
        self.root.mainloop()


def main():
    App().run()
