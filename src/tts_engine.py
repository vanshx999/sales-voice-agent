import os, re, time, asyncio, subprocess, threading, tempfile, wave
from pathlib import Path
from typing import Optional
from .utils import load_settings, load_env

load_env()


def get_tts_engine():
    return MultiProviderTTS()


class SayTTS:
    def __init__(self, config: dict):
        self.voice = config.get("voice", "")
        self.rate = config.get("speed", 1.0)
        self._voice = self._pick_voice()

    def _pick_voice(self) -> str:
        if self.voice:
            return self.voice
        try:
            r = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=5)
            for name in ("Samantha", "Karen", "Moira", "Veena", "Fiona", "Daniel"):
                if name in r.stdout:
                    return name
        except Exception:
            pass
        return "Samantha"

    @property
    def name(self) -> str:
        return f"say({self._voice})"

    def speak(self, text: str, on_word=None):
        rate = int(self.rate * 175)
        subprocess.run(
            ["say", "-v", self._voice, "-r", str(rate)],
            input=text, text=True, capture_output=True, timeout=60,
        )


class ElevenLabsTTS:
    def __init__(self, config: dict):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.voice_id = config.get("voice_id", "")
        self.model = config.get("model", "eleven_flash_v2_5")
        self._client = None
        self._fallback_say = SayTTS({"voice": "Samantha", "speed": 1.0})

    def _get_client(self):
        if self._client is None:
            from elevenlabs import ElevenLabs
            if not self.api_key:
                raise RuntimeError("ELEVENLABS_API_KEY not set")
            self._client = ElevenLabs(api_key=self.api_key)
        return self._client

    @property
    def name(self) -> str:
        return f"elevenlabs({self.voice_id or 'fallback'})"

    def speak(self, text: str, on_word=None):
        client = self._get_client()
        voice_id = self.voice_id or "EXAVITQu4vr4xnSDxMaL"
        try:
            audio = client.text_to_speech.convert(
                text=text, voice_id=voice_id, model_id=self.model,
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
            self._fallback_say.speak(text)

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


class EdgeTTS:
    def __init__(self, config: dict):
        self.voice = config.get("voice", "hi-IN-SwaraNeural")
        self.rate = config.get("speed", 1.0)

    @property
    def name(self) -> str:
        return f"edge({self.voice})"

    def speak(self, text: str, on_word=None):
        try:
            import edge_tts
            temp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_path = temp.name
            temp.close()
            try:
                communicate = edge_tts.Communicate(text, self.voice, rate=f"+{int((self.rate-1)*50)}%")
                asyncio.run(communicate.save(temp_path))
                subprocess.run(["afplay", temp_path], capture_output=True, timeout=60)
            finally:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
        except Exception as e:
            print(f"[EdgeTTS] Error: {e}, falling back to say")
            SayTTS({"voice": "Lekha", "speed": 1.0}).speak(text)


class MultiProviderTTS:
    def __init__(self):
        settings = load_settings()
        lang_config = settings.get("language", {})
        self._providers = lang_config.get("tts_providers", {})
        self._current_language = "en"
        self._engines = {}
        self._prepared = set()

    def _get_engine(self, provider: str, config: dict):
        key = provider + str(config)
        if key not in self._engines:
            if provider == "elevenlabs":
                self._engines[key] = ElevenLabsTTS({**config, "model": "eleven_flash_v2_5"})
            elif provider == "edge":
                self._engines[key] = EdgeTTS(config)
            elif provider == "say":
                self._engines[key] = SayTTS(config)
            else:
                self._engines[key] = SayTTS(config)
        return self._engines[key]

    def _engine_for(self, language: str):
        lang = language or "en"
        provider_config = self._providers.get(lang, self._providers.get("en", {}))
        return self._get_engine(provider_config.get("provider", "say"), provider_config)

    def set_language(self, language: str):
        self._current_language = language or "en"
        engine = self._engine_for(self._current_language)
        print(f"[MultiProviderTTS] Switched to '{self._current_language}' → {engine.name}")

    def speak(self, text: str, on_word=None):
        engine = self._engine_for(self._current_language)
        engine.speak(text, on_word)

    @property
    def name(self) -> str:
        engine = self._engine_for(self._current_language)
        return f"multi({self._current_language}:{engine.name})"
