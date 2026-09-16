from __future__ import annotations

import json
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

from iras import __version__
from iras.config import Settings
from iras.remote_client import IRASRemoteClient
from iras.security.secret_store import protect_secret, unprotect_secret, protection_backend
from iras.device_bridge.agent import (
    DeviceBridgeAgent,
)
from iras.voice.conversation import (
    extract_wake_command,
    is_probable_echo,
    pop_complete_sentences,
)
from iras.voice.stt import Listener
from iras.voice.tts import Speaker


DEFAULT_SERVER = "https://iras-cloud.onrender.com"
CONFIG_PATH = Path.home() / ".iras-client.json"


def load_client_config():
    data = {}

    if CONFIG_PATH.exists():
        try:
            data = json.loads(
                CONFIG_PATH.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            data = {}

    data.setdefault(
        "server_url",
        os.getenv(
            "IRAS_SERVER_URL",
            DEFAULT_SERVER,
        ),
    )
    env_token = os.getenv("IRAS_REMOTE_TOKEN", "").strip()
    if env_token:
        data["token"] = env_token
    else:
        protected = str(data.get("token_protected") or "")
        legacy = str(data.get("token") or "")
        try:
            data["token"] = unprotect_secret(protected or legacy)
        except Exception:
            data["token"] = legacy
    data.setdefault(
        "hands_free",
        True,
    )
    data.setdefault(
        "wake_word",
        "iras",
    )
    return data


def save_client_config(data):
    payload = dict(data or {})
    token = str(payload.pop("token", "") or "")
    payload["token_protected"] = protect_secret(token) if token else ""
    payload["secret_backend"] = protection_backend()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


class IRASRemoteDesktop:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("IRAS")
        self.root.geometry("900x680")
        self.root.minsize(680, 460)

        self.config = load_client_config()
        self.client = None
        self.device_bridge = None
        self.outbox = queue.Queue()
        self.voice_queue = queue.Queue()

        self.manual_listening = False
        self.request_active = False
        self.request_generation = 0
        self.closing = threading.Event()

        self.hands_free = bool(
            self.config.get(
                "hands_free",
                True,
            )
        )
        self.wake_word = str(
            self.config.get(
                "wake_word",
                "iras",
            )
            or "iras"
        ).strip()

        self.conversation_until = 0.0
        self.last_spoken_text = ""
        self.voice_on = True

        settings = Settings.load()

        self.speaker = Speaker(
            settings.tts_provider,
            settings.voice,
            settings.voice_profile,
        )

        self.listener = Listener(
            settings.whisper_model,
            settings.listen_seconds,
        )

        self.chat = tk.Text(
            self.root,
            wrap="word",
            state="disabled",
            font=("Segoe UI", 11),
        )
        self.chat.pack(
            fill="both",
            expand=True,
            padx=12,
            pady=(12, 6),
        )

        row = tk.Frame(self.root)
        row.pack(
            fill="x",
            padx=12,
            pady=(0, 12),
        )

        self.entry = tk.Entry(
            row,
            font=("Segoe UI", 11),
        )
        self.entry.pack(
            side="left",
            fill="x",
            expand=True,
        )
        self.entry.bind(
            "<Return>",
            lambda _e: self.send(),
        )

        self.mic_button = tk.Button(
            row,
            text="Mic",
            command=self.listen,
            width=8,
        )
        self.mic_button.pack(
            side="left",
            padx=(6, 0),
        )

        self.send_button = tk.Button(
            row,
            text="Send",
            command=self.send,
            width=8,
        )
        self.send_button.pack(
            side="left",
            padx=(6, 0),
        )

        tk.Button(
            row,
            text="Voice",
            command=self.toggle_voice,
            width=8,
        ).pack(
            side="left",
            padx=(6, 0),
        )

        self.hands_button = tk.Button(
            row,
            text="Hands-free",
            command=self.toggle_hands_free,
            width=12,
        )
        self.hands_button.pack(
            side="left",
            padx=(6, 0),
        )

        tk.Button(
            row,
            text="Server",
            command=self.configure,
            width=8,
        ).pack(
            side="left",
            padx=(6, 0),
        )

        self.status = tk.StringVar(
            value="Not connected"
        )

        tk.Label(
            self.root,
            textvariable=self.status,
            anchor="w",
        ).pack(
            fill="x",
            padx=12,
            pady=(0, 8),
        )

        self.root.after(
            80,
            self.poll,
        )
        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close,
        )

        self.ensure_config()
        self._update_hands_button()

        threading.Thread(
            target=self._voice_worker,
            daemon=True,
        ).start()

        threading.Thread(
            target=self._handsfree_worker,
            daemon=True,
        ).start()

    def _chat_write(self, text):
        self.chat.configure(
            state="normal"
        )
        self.chat.insert(
            "end",
            text,
        )
        self.chat.see("end")
        self.chat.configure(
            state="disabled"
        )

    def add(self, who, text):
        self._chat_write(
            f"{who}: {text}\n\n"
        )

    def begin_stream(self):
        self._chat_write(
            "IRAS: "
        )

    def append_stream(self, text):
        self._chat_write(text)

    def end_stream(self):
        self._chat_write(
            "\n\n"
        )

    def ensure_config(self):
        if not self.config.get(
            "token"
        ):
            self.configure()
        self.rebuild_client()

    def configure(self):
        url = simpledialog.askstring(
            "IRAS Server",
            (
                "Server URL "
                "(default: "
                f"{DEFAULT_SERVER})"
            ),
            initialvalue=self.config.get(
                "server_url",
                DEFAULT_SERVER,
            ),
            parent=self.root,
        )
        if url is None:
            return

        token = simpledialog.askstring(
            "IRAS Access Token",
            "IRAS access token:",
            initialvalue=self.config.get(
                "token",
                "",
            ),
            show="*",
            parent=self.root,
        )
        if token is None:
            return

        clean_url = (
            url.strip().rstrip("/")
            or DEFAULT_SERVER
        )

        self.config.update(
            {
                "server_url": clean_url,
                "token": token.strip(),
                "hands_free": self.hands_free,
                "wake_word": self.wake_word,
            }
        )
        save_client_config(
            self.config
        )
        self.rebuild_client()

    def _stop_device_bridge(self):
        if self.device_bridge is not None:
            try:
                self.device_bridge.stop()
            except Exception:
                pass

        self.device_bridge = None

    def _start_device_bridge(self):
        self._stop_device_bridge()

        if not (
            self.config.get("server_url")
            and self.config.get("token")
        ):
            return

        self.device_bridge = (
            DeviceBridgeAgent(
                self.config["server_url"],
                self.config["token"],
                status_callback=(
                    lambda message:
                    self.outbox.put(
                        (
                            "bridge_status",
                            message,
                        )
                    )
                ),
            )
        )

        self.device_bridge.start()

    def rebuild_client(self):
        self._stop_device_bridge()

        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass

        if (
            self.config.get("server_url")
            and self.config.get("token")
        ):
            self.client = IRASRemoteClient(
                self.config["server_url"],
                self.config["token"],
            )
            self._start_device_bridge()
            self._ready_status()
        else:
            self.client = None
            self.status.set(
                "Server/token not configured"
            )

    def _ready_status(self):
        if self.hands_free:
            self.status.set(
                "Hands-free · "
                f'say "{self.wake_word}"'
            )
        else:
            self.status.set(
                "Ready · streaming · "
                f"{self.speaker.profile.label}"
            )

    def _update_hands_button(self):
        self.hands_button.configure(
            text=(
                "Hands-free On"
                if self.hands_free
                else "Hands-free Off"
            )
        )

    def toggle_hands_free(self):
        self.hands_free = (
            not self.hands_free
        )
        self.config[
            "hands_free"
        ] = self.hands_free
        save_client_config(
            self.config
        )
        self._update_hands_button()
        self._ready_status()

    def toggle_voice(self):
        self.voice_on = (
            not self.voice_on
        )
        if not self.voice_on:
            self._clear_voice()
        self.status.set(
            "Voice "
            f"{'on' if self.voice_on else 'off'}"
        )

    def listen(self):
        if self.manual_listening:
            return

        if not self.client:
            messagebox.showerror(
                "IRAS",
                "Configure the server first.",
            )
            return

        self.manual_listening = True
        self.mic_button.configure(
            state="disabled",
            text="Listening",
        )
        self.status.set(
            "Listening..."
        )
        self._clear_voice()

        threading.Thread(
            target=self._listen_worker,
            daemon=True,
        ).start()

    def _listen_worker(self):
        try:
            text = (
                self.listener
                .listen_once()
            )
            if not text:
                self.outbox.put(
                    ("mic_empty", "")
                )
                return
            self.outbox.put(
                ("heard", text)
            )
        except Exception as exc:
            self.outbox.put(
                ("mic_error", str(exc))
            )

    def send(self):
        text = (
            self.entry.get()
            .strip()
        )
        if not text:
            return
        self.entry.delete(
            0,
            "end",
        )
        self.send_text(text)

    def send_text(
        self,
        text: str,
        *,
        interrupt: bool = False,
    ):
        text = str(
            text
            or ""
        ).strip()

        if not text:
            return

        if not self.client:
            messagebox.showerror(
                "IRAS",
                "Configure the server first.",
            )
            return

        if (
            self.request_active
            and not interrupt
        ):
            return

        if interrupt:
            self.request_generation += 1
            self.request_active = False
            self._clear_voice()

        self.request_generation += 1
        generation = (
            self.request_generation
        )

        self.request_active = True
        self.send_button.configure(
            state="disabled"
        )
        self.add(
            "You",
            text,
        )
        self.status.set(
            "IRAS is thinking..."
        )

        threading.Thread(
            target=self._request,
            args=(text, generation),
            daemon=True,
        ).start()

    def _request(
        self,
        text: str,
        generation: int,
    ):
        parts = []
        speech_buffer = ""

        try:
            self.outbox.put(
                ("stream_start", generation)
            )

            for item in (
                self.client
                .chat_stream(text)
            ):
                if (
                    generation
                    != self.request_generation
                ):
                    return

                event = item.get(
                    "event"
                )
                data = (
                    item.get("data")
                    or {}
                )

                if event == "token":
                    chunk = (
                        data.get("text")
                        or ""
                    )
                    if chunk:
                        parts.append(chunk)
                        self.outbox.put(
                            (
                                "stream_token",
                                (
                                    generation,
                                    chunk,
                                ),
                            )
                        )
                        speech_buffer += chunk
                        (
                            sentences,
                            speech_buffer,
                        ) = pop_complete_sentences(
                            speech_buffer
                        )
                        for sentence in sentences:
                            self._enqueue_voice(
                                sentence,
                                generation,
                            )

                elif event == "done":
                    (
                        sentences,
                        speech_buffer,
                    ) = pop_complete_sentences(
                        speech_buffer,
                        force=True,
                    )
                    for sentence in sentences:
                        self._enqueue_voice(
                            sentence,
                            generation,
                        )

                    self.outbox.put(
                        (
                            "stream_done",
                            {
                                "generation": generation,
                                "text": "".join(parts),
                                "meta": data,
                            },
                        )
                    )

                elif event == "error":
                    raise RuntimeError(
                        data.get("message")
                        or "Streaming failed."
                    )

        except Exception as exc:
            if (
                generation
                == self.request_generation
            ):
                self.outbox.put(
                    (
                        "error",
                        (
                            generation,
                            str(exc),
                        ),
                    )
                )

    def _enqueue_voice(
        self,
        text: str,
        generation: int | None = None,
    ):
        if (
            not self.voice_on
            or not text.strip()
        ):
            return
        self.voice_queue.put(
            (
                generation,
                text.strip(),
            )
        )

    def _clear_voice(self):
        self.speaker.stop()
        try:
            while True:
                self.voice_queue.get_nowait()
                self.voice_queue.task_done()
        except queue.Empty:
            pass

    def _voice_worker(self):
        while (
            not self.closing.is_set()
        ):
            try:
                generation, text = (
                    self.voice_queue.get(
                        timeout=0.3
                    )
                )
            except queue.Empty:
                continue

            try:
                if (
                    generation is not None
                    and generation
                    != self.request_generation
                ):
                    continue

                self.last_spoken_text = (
                    text
                )
                self.outbox.put(
                    ("speaking", text)
                )

                backend = (
                    self.speaker
                    .speak(text)
                )
                self.outbox.put(
                    ("spoken", backend)
                )
            except Exception as exc:
                self.outbox.put(
                    ("voice_error", str(exc))
                )
            finally:
                self.voice_queue.task_done()

    def _handsfree_worker(self):
        while (
            not self.closing.is_set()
        ):
            if (
                not self.hands_free
                or self.manual_listening
                or not self.client
            ):
                time.sleep(0.25)
                continue

            try:
                text = (
                    self.listener
                    .listen_phrase(
                        start_timeout=2.0,
                        max_seconds=10.0,
                        silence_seconds=0.70,
                    )
                )

                if not text:
                    continue

                if is_probable_echo(
                    text,
                    self.last_spoken_text,
                    wake_word=self.wake_word,
                ):
                    continue

                armed = (
                    time.monotonic()
                    < self.conversation_until
                )

                (
                    accepted,
                    command,
                ) = extract_wake_command(
                    text,
                    self.wake_word,
                    armed=armed,
                )

                if not accepted:
                    continue

                self._clear_voice()

                if not command:
                    self.conversation_until = (
                        time.monotonic()
                        + 8.0
                    )
                    self.outbox.put(
                        ("wake_only", "")
                    )
                    continue

                self.conversation_until = (
                    time.monotonic()
                    + 20.0
                )
                self.outbox.put(
                    (
                        "handsfree_command",
                        command,
                    )
                )

            except Exception as exc:
                self.outbox.put(
                    (
                        "handsfree_error",
                        str(exc),
                    )
                )
                time.sleep(1.0)

    def poll(self):
        try:
            while True:
                (
                    kind,
                    value,
                ) = (
                    self.outbox
                    .get_nowait()
                )

                if kind == "stream_start":
                    if (
                        value
                        != self.request_generation
                    ):
                        continue
                    self.begin_stream()
                    self.status.set(
                        "IRAS is replying..."
                    )

                elif kind == "stream_token":
                    (
                        generation,
                        chunk,
                    ) = value
                    if (
                        generation
                        != self.request_generation
                    ):
                        continue
                    self.append_stream(chunk)

                elif kind == "stream_done":
                    generation = (
                        value.get(
                            "generation"
                        )
                    )
                    if (
                        generation
                        != self.request_generation
                    ):
                        continue

                    self.end_stream()
                    self.request_active = False
                    self.send_button.configure(
                        state="normal"
                    )
                    self.conversation_until = (
                        time.monotonic()
                        + 20.0
                    )

                    meta = (
                        value.get("meta")
                        or {}
                    )
                    first = int(
                        meta.get(
                            "first_token_ms",
                            0,
                        )
                        or 0
                    )

                    if self.hands_free:
                        self.status.set(
                            "Listening for your "
                            "next sentence..."
                        )
                    elif first:
                        self.status.set(
                            "Ready · first token "
                            f"{first / 1000:.2f}s"
                        )
                    else:
                        self._ready_status()

                elif kind == "handsfree_command":
                    self.send_text(
                        value,
                        interrupt=True,
                    )

                elif kind == "wake_only":
                    self.status.set(
                        "Yeah? I'm listening."
                    )
                    self._enqueue_voice(
                        "Yeah?",
                        None,
                    )

                elif kind == "heard":
                    self.manual_listening = False
                    self.mic_button.configure(
                        state="normal",
                        text="Mic",
                    )
                    self.send_text(
                        value,
                        interrupt=self.request_active,
                    )

                elif kind == "mic_empty":
                    self.manual_listening = False
                    self.mic_button.configure(
                        state="normal",
                        text="Mic",
                    )
                    self._ready_status()

                elif kind == "mic_error":
                    self.manual_listening = False
                    self.mic_button.configure(
                        state="normal",
                        text="Mic",
                    )
                    self.status.set(
                        "Microphone unavailable"
                    )
                    messagebox.showerror(
                        "IRAS Microphone",
                        value,
                    )

                elif kind == "speaking":
                    self.status.set(
                        "IRAS is speaking · "
                        "say IRAS to interrupt"
                    )

                elif kind == "spoken":
                    if (
                        self.hands_free
                        and not self.request_active
                    ):
                        self.status.set(
                            "Listening..."
                        )

                elif kind == "bridge_status":
                    if (
                        "paired securely"
                        in value
                    ):
                        self.status.set(
                            "PC bridge online"
                        )

                elif kind == "voice_error":
                    self.status.set(
                        "Voice unavailable"
                    )

                elif kind == "handsfree_error":
                    self.status.set(
                        "Hands-free microphone "
                        "temporarily unavailable"
                    )

                elif kind == "error":
                    (
                        generation,
                        message,
                    ) = value
                    if (
                        generation
                        != self.request_generation
                    ):
                        continue

                    if self.request_active:
                        self.end_stream()

                    self.request_active = False
                    self.send_button.configure(
                        state="normal"
                    )
                    self.add(
                        "Error",
                        message,
                    )
                    self.status.set(
                        "AI provider unavailable"
                    )

        except queue.Empty:
            pass

        self.root.after(
            80,
            self.poll,
        )

    def close(self):
        self.closing.set()
        self._clear_voice()
        self._stop_device_bridge()

        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass

        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    import argparse
    parser = argparse.ArgumentParser(prog="iras-remote", description="IRAS remote desktop client")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args()
    IRASRemoteDesktop().run()


if __name__ == "__main__":
    main()
