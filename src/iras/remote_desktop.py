from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

from iras.config import Settings
from iras.remote_client import IRASRemoteClient
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

    data.setdefault(
        "token",
        os.getenv(
            "IRAS_REMOTE_TOKEN",
            "",
        ),
    )

    return data


def save_client_config(data):
    CONFIG_PATH.write_text(
        json.dumps(
            data,
            indent=2,
        ),
        encoding="utf-8",
    )


class IRASRemoteDesktop:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("IRAS")
        self.root.geometry("820x650")
        self.root.minsize(600, 440)

        self.config = load_client_config()
        self.client = None
        self.outbox = queue.Queue()

        voice_settings = Settings.load()

        # Important: Speaker expects provider/voice/profile values,
        # not the Settings object itself. Passing the Settings object
        # caused the old remote EXE to fall back to Windows SAPI.
        self.speaker = Speaker(
            voice_settings.tts_provider,
            voice_settings.voice,
            voice_settings.voice_profile,
        )

        self.voice_on = True

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

        tk.Button(
            row,
            text="Send",
            command=self.send,
            width=9,
        ).pack(
            side="left",
            padx=(6, 0),
        )

        tk.Button(
            row,
            text="Voice",
            command=self.toggle_voice,
            width=9,
        ).pack(
            side="left",
            padx=(6, 0),
        )

        tk.Button(
            row,
            text="Server",
            command=self.configure,
            width=9,
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
            100,
            self.poll,
        )

        self.ensure_config()

    def add(self, who, text):
        self.chat.configure(
            state="normal"
        )

        self.chat.insert(
            "end",
            f"{who}: {text}\n\n",
        )

        self.chat.see("end")

        self.chat.configure(
            state="disabled"
        )

    def ensure_config(self):
        if (
            not self.config.get("token")
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

        self.config = {
            "server_url": clean_url,
            "token": token.strip(),
        }

        save_client_config(
            self.config
        )

        self.rebuild_client()

    def rebuild_client(self):
        if (
            self.config.get("server_url")
            and self.config.get("token")
        ):
            self.client = IRASRemoteClient(
                self.config["server_url"],
                self.config["token"],
            )

            self.status.set(
                "Ready · "
                f"{self.config['server_url']} · "
                f"{self.speaker.profile.label}"
            )
        else:
            self.client = None
            self.status.set(
                "Server/token not configured"
            )

    def toggle_voice(self):
        self.voice_on = not self.voice_on

        self.status.set(
            "Voice "
            f"{'on' if self.voice_on else 'off'} "
            "· "
            f"{self.speaker.profile.label}"
        )

    def send(self):
        text = self.entry.get().strip()

        if not text:
            return

        if not self.client:
            messagebox.showerror(
                "IRAS",
                "Configure the server first.",
            )
            return

        self.entry.delete(
            0,
            "end",
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
            args=(text,),
            daemon=True,
        ).start()

    def _request(self, text):
        try:
            reply = self.client.chat(text)

            self.outbox.put(
                ("ok", reply)
            )

        except Exception as exc:
            self.outbox.put(
                ("error", str(exc))
            )

    def poll(self):
        try:
            while True:
                kind, value = (
                    self.outbox
                    .get_nowait()
                )

                if kind == "ok":
                    self.add(
                        "IRAS",
                        value,
                    )

                    self.status.set(
                        "Ready"
                    )

                    if self.voice_on:
                        threading.Thread(
                            target=self._speak,
                            args=(value,),
                            daemon=True,
                        ).start()

                else:
                    self.add(
                        "Error",
                        value,
                    )

                    self.status.set(
                        "Connection failed"
                    )

        except queue.Empty:
            pass

        self.root.after(
            100,
            self.poll,
        )

    def _speak(self, text):
        try:
            self.status.set(
                "IRAS is speaking..."
            )

            backend = (
                self.speaker
                .speak(text)
            )

            self.root.after(
                0,
                lambda: self.status.set(
                    "Ready · "
                    f"{self.speaker.profile.label} · "
                    f"{backend}"
                ),
            )

        except Exception as exc:
            self.root.after(
                0,
                lambda: self.status.set(
                    "Voice unavailable"
                ),
            )

    def run(self):
        self.root.mainloop()


def main():
    IRASRemoteDesktop().run()


if __name__ == "__main__":
    main()
