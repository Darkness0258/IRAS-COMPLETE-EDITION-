from __future__ import annotations
from pathlib import Path
import tempfile
class Listener:
    def __init__(self,model='base.en',seconds=6): self.model_name=model; self.seconds=seconds; self._model=None
    def listen_once(self):
        try: import sounddevice as sd; import soundfile as sf; from faster_whisper import WhisperModel
        except ImportError as e: raise RuntimeError("Install microphone support with: pip install -e '.[voice]'") from e
        sr=16000; audio=sd.rec(int(self.seconds*sr),samplerate=sr,channels=1,dtype='float32'); sd.wait()
        with tempfile.NamedTemporaryFile(suffix='.wav',delete=False) as f: path=Path(f.name)
        try:
            sf.write(path,audio,sr)
            if self._model is None: self._model=WhisperModel(self.model_name,device='cpu',compute_type='int8')
            segs,_=self._model.transcribe(str(path),vad_filter=True); return ' '.join(s.text.strip() for s in segs).strip()
        finally:
            try: path.unlink()
            except OSError: pass
