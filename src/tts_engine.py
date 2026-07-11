import os, re, time, subprocess, threading, tempfile, wave
from pathlib import Path
from typing import Optional
from .utils import load_settings, load_env

load_env()


def get_tts_engine():
    settings = load_settings()
    provider = settings["tts"]["provider"]
    if provider == "elevenlabs":
        return ElevenLabsTTS(settings["tts"])
    elif provider == "piper":
        return PiperTTS(settings["tts"])
    else:
        return SayTTS(settings["tts"])


class SayTTS:
    def __init__(self, config: dict):
        self.voice = self._pick_voice()
        self.rate = config.get("speed", 180)

    def _pick_voice(self) -> str:
        try:
            r = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=5)
            for name in ("Samantha", "Karen", "Moira", "Veena", "Fiona", "Daniel"):
                if name in r.stdout:
                    return name
        except Exception:
            pass
        return "Samantha"

    def speak(self, text: str, on_word=None):
        subprocess.run(
            ["say", "-v", self.voice, "-r", str(int(self.rate * 175))],
            input=text, text=True, capture_output=True, timeout=60,
        )

    @property
    def name(self) -> str:
        return f"say({self.voice})"


class ElevenLabsTTS:
    def __init__(self, config: dict):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.voice_id = config.get("voice_id", "")
        self.model = config.get("model", "eleven_flash_v2_5")
        self._client = None
        self._fallback = SayTTS(config)
        self._voice_map = {}
        lang_config = load_settings().get("language", {})
        self._voice_map = lang_config.get("tts_voice_map", {})
        self._current_language = "en"

    def set_language(self, language: str):
        self._current_language = language
        if language in self._voice_map:
            self.voice_id = self._voice_map[language]
            print(f"[ElevenLabsTTS] Switched to language '{language}' → voice {self.voice_id}")

    def _get_client(self):
        if self._client is None:
            from elevenlabs import ElevenLabs
            if not self.api_key:
                raise RuntimeError("ELEVENLABS_API_KEY not set")
            self._client = ElevenLabs(api_key=self.api_key)
        return self._client

    def speak(self, text: str, on_word=None):
        client = self._get_client()
        if not self.voice_id:
            voice_id = self._pick_free_voice(client)
            if not voice_id:
                print("[ElevenLabsTTS] No usable voice, falling back to say")
                return self._fallback.speak(text)
            self.voice_id = voice_id
        try:
            audio = client.text_to_speech.convert(
                text=text, voice_id=self.voice_id, model_id=self.model,
            )
            temp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            temp_path = temp.name
            temp.close()
            try:
                with open(temp_path, "wb") as f:
                    for chunk in audio:
                        f.write(chunk)
                subprocess.run(["afplay", temp_path], capture_output=True, timeout=60)
            finally:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
        except Exception as e:
            print(f"[ElevenLabsTTS] API error: {e}")
            print("[ElevenLabsTTS] Falling back to system voice")
            self._fallback.speak(text)

    def _pick_free_voice(self, client) -> str:
        try:
            voices = client.voices.get_all()
            for v in voices.voices:
                if v.category == "free" or v.category == "cloned" or v.category == "generated":
                    print(f"[ElevenLabsTTS] Using free voice: {v.name} ({v.voice_id})")
                    return v.voice_id
        except Exception as e:
            print(f"[ElevenLabsTTS] Voice list error: {e}")
        return ""

    def clone_voice(self, name: str, audio_files: list[str]) -> str:
        client = self._get_client()
        from elevenlabs import Voice
        voice = client.voices.add(
            name=name,
            files=audio_files,
        )
        self.voice_id = voice.voice_id
        print(f"[ElevenLabsTTS] Cloned voice '{name}' → {voice.voice_id}")
        return voice.voice_id

    @property
    def name(self) -> str:
        return f"elevenlabs({self.voice_id or 'fallback'})"


class PiperTTS:
    def __init__(self, config: dict):
        self.voice = config.get("voice", "en_US-lessac-medium")
        self.piper_path = config.get("piper_path", "piper")
        self.model_dir = Path(config.get("model_dir", os.path.expanduser("~/.piper/models")))

    def _ensure_model(self) -> Optional[Path]:
        model_file = self.model_dir / f"{self.voice}.onnx"
        if not model_file.exists():
            print(f"[PiperTTS] Model not found at {model_file}. Download with:")
            print(f"  mkdir -p {self.model_dir} && cd {self.model_dir}")
            print(f"  wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx")
            print(f"  wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json")
            return None
        return model_file

    def speak(self, text: str, on_word=None):
        model_file = self._ensure_model()
        if model_file is None:
            return SayTTS({"speed": 1.0}).speak(text)
        temp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_path = temp.name
        temp.close()
        try:
            proc = subprocess.Popen(
                [self.piper_path, "--model", str(model_file), "--output-file", temp_path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            proc.communicate(input=text.encode("utf-8"), timeout=30)
            subprocess.run(["afplay", temp_path], capture_output=True, timeout=60)
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    @property
    def name(self) -> str:
        return f"piper({self.voice})"
