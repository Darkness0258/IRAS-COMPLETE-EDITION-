from __future__ import annotations
import os,shutil,sys,importlib.util
from pathlib import Path

def run(settings):
    checks=[]
    def add(name,ok,detail): checks.append((name,ok,detail))
    add('Python >= 3.11',sys.version_info>=(3,11),sys.version.split()[0])
    add('Git',bool(shutil.which('git')),shutil.which('git') or 'not found')
    mpv=shutil.which('mpv') or (r'C:\Program Files\MPV Player\mpv.exe' if os.name=='nt' and Path(r'C:\Program Files\MPV Player\mpv.exe').exists() else None)
    add('MPV voice playback',bool(mpv),mpv or 'not found')
    add('Edge TTS',importlib.util.find_spec('edge_tts') is not None,'installed' if importlib.util.find_spec('edge_tts') else 'missing')
    add('Playwright (optional)',importlib.util.find_spec('playwright') is not None,'installed' if importlib.util.find_spec('playwright') else 'optional extra not installed')
    add('Local Whisper (optional)',importlib.util.find_spec('faster_whisper') is not None,'installed' if importlib.util.find_spec('faster_whisper') else 'optional extra not installed')
    add('Brain configured',settings.provider=='demo' or settings.provider=='ollama' or bool(settings.api_key),settings.provider)
    return checks
