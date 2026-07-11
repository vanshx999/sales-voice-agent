import os, re, time, queue, threading, wave, tempfile
from typing import Optional, Callable
from .utils import load_settings
from .tts_engine import get_tts_engine
from .meeting_linker import get_meeting_linker

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

try:
    import pyaudio
    import numpy as np
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False


_LANG_ASK_EN = "Would you like to continue in English or Hindi?"
_LANG_ASK_HI = "Aap Hindi mein baat karenge ya English mein?"


class VoiceAgent:
    def __init__(self, conversation_engine=None, use_mic=False):
        self.settings = load_settings()
        self.engine = conversation_engine
        self.is_calling = False
        self.is_speaking = False
        self.should_stop = False
        self._interrupted = False
        self._tts = get_tts_engine()
        self._whisper_model = None
        self._interrupt_lock = threading.Lock()
        self._use_mic = use_mic and PYAUDIO_AVAILABLE and os.isatty(0)
        self._vad_threshold = self.settings["call"].get("vad_threshold", 0.03)
        self._meeting_linker = get_meeting_linker()
        self._pa = None
        self._callbacks = {
            "speech_start": [], "speech_end": [],
            "interruption": [], "call_end": [],
        }

    def on(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _emit(self, event: str, *args, **kwargs):
        for cb in self._callbacks.get(event, []):
            cb(*args, **kwargs)

    # ── Language Selection ───────────────────────────────────────

    def _ask_language(self) -> str:
        self._speak(_LANG_ASK_EN)
        time.sleep(0.5)
        self._speak(_LANG_ASK_HI)
        response = self._listen()
        if response:
            response = response.lower().strip()
            if "angrezi" in response or "english" in response or "inglish" in response:
                return "en"
            if "hinglish" in response or "mix" in response or "dono" in response:
                return "hinglish"
            if "hind" in response or "hindi" in response or "desi" in response:
                return "hi"
        return "hinglish"

    def _set_language(self, language: str):
        self._lead_language = language
        if hasattr(self._tts, "set_language"):
            self._tts.set_language(language)
        if self.engine:
            self.engine.language = language
            self.engine.lead_info["language"] = language
        print(f"[VoiceAgent] Language set to: {language}")

    # ── Call Flow ─────────────────────────────────────────────────

    def make_call(self, phone_number: str, lead) -> dict:
        self.is_calling = True
        self.should_stop = False
        self._pa = pyaudio.PyAudio() if self._use_mic else None
        lead_lang = getattr(lead, "language", "") or self.settings.get("language", {}).get("default", "hinglish")
        self._lead_language = lead_lang
        if hasattr(self._tts, "set_language"):
            self._tts.set_language(lead_lang)
        print(f"\n{'='*60}")
        print(f"[VoiceAgent] Calling {lead.name} at {phone_number}")
        print(f"[VoiceAgent] TTS engine: {self._tts.name}")
        print(f"[VoiceAgent] Language: {self._lead_language}")
        print(f"{'='*60}\n")
        self._emit("call_start", lead)
        if self.engine:
            self.engine.start_call(lead)
            greeting = self.engine.generate_greeting()
            self._speak(greeting)
        if self.settings.get("language", {}).get("ask_at_start", True):
            chosen = self._ask_language()
            self._set_language(chosen)
        result = self._run_conversation_loop(lead)
        self.is_calling = False
        if self._pa:
            self._pa.terminate()
            self._pa = None
        self._emit("call_end", lead, result)
        return result

    def _run_conversation_loop(self, lead) -> dict:
        max_turns = 30
        turn = 0
        outcome = "no_answer"
        while turn < max_turns and not self.should_stop:
            turn += 1
            print(f"\n--- Turn {turn} ---")
            user_input = self._listen()
            if not user_input:
                if turn == 1:
                    print("[VoiceAgent] No answer")
                    outcome = "no_answer"
                break
            user_input = user_input.strip().lower()
            print(f"[Lead] {user_input}")
            if self._is_end_call_signal(user_input):
                self._speak(self._generate_farewell())
                outcome = "not_interested"
                break
            if not self.engine:
                continue
            objection = self._detect_objection(user_input)
            reply = self.engine.handle_objection(objection) if objection else self.engine.process_input(user_input)
            print(f"[Agent] {reply}")
            self._speak(reply)
            if self._detect_not_interested(user_input):
                outcome = "not_interested"
                break
            if self._detect_meeting_interest(user_input, reply):
                outcome = "meeting_booked" if self._book_meeting() else "interested"
                break
        else:
            outcome = "timeout"
        return self._build_call_result(lead, outcome)

    # ── Speech Output ──────────────────────────────────────────────

    def _speak(self, text: str):
        self.is_speaking = True
        self._interrupted = False
        self._emit("speech_start", text)
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
        try:
            for i, sentence in enumerate(sentences):
                if self.should_stop or self._interrupted:
                    break
                print(f"[VoiceAgent says]: {sentence}")
                self._tts.speak(sentence)
                pause = self._natural_pause(i, len(sentences), sentence)
                if not self._interrupted:
                    time.sleep(pause)
        except Exception as e:
            print(f"[VoiceAgent] Speak error: {e}")
        self.is_speaking = False
        self._emit("speech_end")

    def _natural_pause(self, index: int, total: int, sentence: str) -> float:
        base = self.settings["call"]["pause_between_sentences_ms"] / 1000
        if index == total - 1:
            return base * 0.5
        if sentence.endswith("?"):
            return base * 1.5
        words = len(sentence.split())
        if words > 15:
            return base * 1.3
        if words < 4:
            return base * 0.7
        return base

    # ── Audio Input (PyAudio) ──────────────────────────────────────

    def _listen(self) -> Optional[str]:
        if self._use_mic and not getattr(self, "_mic_failed", False):
            return self._listen_mic()
        return self._text_input_fallback()

    def _listen_mic(self) -> Optional[str]:
        fs = self.settings["voice"]["sample_rate"]
        max_dur = self.settings["call"]["no_answer_timeout_seconds"]
        chunk_sec = 0.3
        chunk = int(fs * chunk_sec)
        max_chunks = int(max_dur / chunk_sec)
        silence_limit = int(1.2 / chunk_sec)
        print(f"[VoiceAgent] Listening... (max {max_dur}s)")
        try:
            stream = self._pa.open(
                format=pyaudio.paInt16, channels=1, rate=int(fs),
                input=True, frames_per_buffer=chunk,
            )
            noise_floor = 0
            for _ in range(4):
                data = stream.read(chunk, exception_on_overflow=False)
                arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                noise_floor = max(noise_floor, np.max(np.abs(arr)))
            threshold = max(noise_floor * 3, 800)
            frames = []
            speech_chunks = 0
            silent_chunks = 0
            started = False
            for i in range(max_chunks):
                data = stream.read(chunk, exception_on_overflow=False)
                frames.append(data)
                arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                level = np.max(np.abs(arr))
                if level > threshold:
                    if not started:
                        print("[VoiceAgent] Speech started")
                        started = True
                    speech_chunks += 1
                    silent_chunks = 0
                elif started:
                    silent_chunks += 1
                    if silent_chunks >= silence_limit:
                        print(f"[VoiceAgent] Silence detected, stopping")
                        break
            stream.stop_stream()
            stream.close()
            if not started or speech_chunks < 1:
                print("[VoiceAgent] Silence")
                return None
            audio_data = b"".join(frames)
            arr = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            return self._transcribe(arr, fs)
        except Exception as e:
            print(f"[VoiceAgent] Mic error: {e}")
            self._mic_failed = True
            print("[VoiceAgent] Mic disabled, using text")
            return self._text_input_fallback()

    def _text_input_fallback(self) -> str:
        try:
            return input("[You] ")
        except (EOFError, KeyboardInterrupt):
            return ""

    def _transcribe(self, audio, sample_rate) -> str:
        if WHISPER_AVAILABLE:
            try:
                if self._whisper_model is None:
                    print("[VoiceAgent] Loading Whisper...")
                    self._whisper_model = whisper.load_model("base")
                lang = "hi" if self._lead_language in ("hi", "hinglish") else "en"
                text = self._whisper_model.transcribe(
                    audio.flatten().astype(np.float32), language=lang,
                )["text"].strip()
                if text:
                    print(f"[VoiceAgent] Heard: {text}")
                    return text
            except Exception as e:
                print(f"[VoiceAgent] Whisper error: {e}")
        return self._text_input_fallback()

    # ── Intent Detection ───────────────────────────────────────────

    def _is_end_call_signal(self, text: str) -> bool:
        return any(p in text for p in [
            "goodbye", "bye", "hang up", "end call", "that's all", "i have to go",
            "alvida", "bye bye", "rakhiye",
        ])

    def _detect_objection(self, text: str) -> Optional[str]:
        for kw in ["too expensive", "not interested", "no budget", "too busy",
                    "happy with current", "not now", "maybe later", "call me back",
                    "don't need", "waste of time", "not the right time",
                    "mehanga", "paisa nahi", "budget nahi", "interested nahi"]:
            if kw in text:
                return kw
        return None

    def _detect_meeting_interest(self, user_input: str, agent_reply: str) -> bool:
        return any(p in user_input.lower() for p in [
            "book a meeting", "book a call", "schedule a meeting", "schedule a call",
            "set up a meeting", "set up a call", "let's do it", "let's schedule",
            "yes please book", "yes please schedule", "sign me up",
            "meeting book karo", "call schedule karo", "haan karo", "theek hai karo",
        ])

    def _detect_not_interested(self, text: str) -> bool:
        return any(p in text for p in [
            "not interested", "no thanks", "don't call me", "stop calling",
            "leave me alone", "take me off", "do not call", "unsubscribe",
            "interest nahi", "nahi chahiye", "mat karo",
        ])

    def _book_meeting(self) -> bool:
        print("\n[VoiceAgent] Booking meeting...")
        self._speak("I'd love to get something on the calendar. What date and time works best for you?")
        meeting_time = self._listen()
        if meeting_time:
            print(f"[VoiceAgent] Proposed meeting: {meeting_time}")
            meeting_data = self._meeting_linker.create_meeting(
                title=f"Sales Call - {self.engine.lead_info.get('name', 'Prospect')}",
                date_time=meeting_time,
            )
            self._meeting_time = meeting_time
            self._meeting_link = meeting_data["link"]
            print(f"[VoiceAgent] Meeting link: {self._meeting_link}")
            self._speak(f"Perfect, I've noted {meeting_time}. I'll send a calendar invite with the meeting link to confirm.")
            return True
        self._speak("No problem, I'll follow up via email with some available times.")
        return True

    def _generate_farewell(self) -> str:
        return "Thank you for your time. Have a great day!"

    def _build_call_result(self, lead, outcome: str) -> dict:
        summary_data, qualification = {}, {}
        if self.engine:
            summary_data = self.engine.generate_summary()
            qualification = self.engine.qualify_lead()
        return {
            "lead_id": lead.id,
            "outcome": outcome,
            "summary": summary_data.get("summary", ""),
            "requirements": summary_data.get("requirements", ""),
            "objections": summary_data.get("objections", ""),
            "next_steps": summary_data.get("next_steps", ""),
            "follow_up": summary_data.get("follow_up", ""),
            "qualification": qualification.get("qualified", "unknown"),
            "meeting_date": getattr(self, "_meeting_time", summary_data.get("meeting_date", "")),
            "meeting_link": getattr(self, "_meeting_link", ""),
            "language": self._lead_language,
        }

    def stop(self):
        self.should_stop = True
        self.is_calling = False
