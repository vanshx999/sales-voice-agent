import os, re, time, queue, threading
from typing import Optional, Callable
from .utils import load_settings
from .tts_engine import get_tts_engine
from .meeting_linker import get_meeting_linker

try:
    import sounddevice as sd
    import numpy as np
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False


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
        self._use_mic = use_mic and SOUNDDEVICE_AVAILABLE and os.isatty(0)
        self._vad_threshold = self.settings["call"].get("vad_threshold", 0.03)
        self._meeting_linker = get_meeting_linker()
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

    def make_call(self, phone_number: str, lead) -> dict:
        self.is_calling = True
        self.should_stop = False
        self._lead_language = getattr(lead, "language", "") or self.settings.get("language", {}).get("default", "hinglish")
        if hasattr(self._tts, "set_language"):
            self._tts.set_language(self._lead_language)
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
        result = self._run_conversation_loop(lead)
        self.is_calling = False
        self._emit("call_end", lead, result)
        return result

    # ── Conversation Loop ──────────────────────────────────────────

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
        vad_thread = None
        if self._use_mic:
            vad_thread = threading.Thread(target=self._vad_monitor, daemon=True)
            vad_thread.start()
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
        if self._interrupted:
            self._emit("interruption")

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

    def _vad_monitor(self):
        fs = self.settings["voice"]["sample_rate"]
        chunk_sec = 0.25
        chunk_frames = int(fs * chunk_sec)
        hits = 0
        required_hits = 3
        while self.is_speaking and not self._interrupted and not self.should_stop:
            try:
                chunk = sd.rec(chunk_frames, samplerate=fs, channels=1, dtype="float32")
                sd.wait()
                level = np.max(np.abs(chunk))
                if level > self._vad_threshold:
                    hits += 1
                    if hits >= required_hits:
                        with self._interrupt_lock:
                            self._interrupted = True
                        print("[VoiceAgent] Interruption detected")
                        break
                else:
                    hits = max(0, hits - 1)
            except Exception:
                break

    # ── Audio Input ────────────────────────────────────────────────

    def _listen(self) -> Optional[str]:
        if self._use_mic and not getattr(self, "_mic_failed", False):
            return self._listen_mic()
        return self._text_input_fallback()

    def _listen_mic(self) -> Optional[str]:
        try:
            fs = self.settings["voice"]["sample_rate"]
            max_dur = self.settings["call"]["no_answer_timeout_seconds"]
            print(f"[VoiceAgent] Listening ({max_dur}s)...")
            recording = sd.rec(int(fs * max_dur), samplerate=int(fs), channels=1, dtype="float32")
            sd.wait()
            if np.max(np.abs(recording)) < self._vad_threshold:
                print("[VoiceAgent] Silence")
                return None
            return self._transcribe(recording, fs)
        except Exception as e:
            print(f"[VoiceAgent] Mic error: {e}")
            self._mic_failed = True
            print("[VoiceAgent] Mic disabled for this call, using text input")
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
                text = self._whisper_model.transcribe(
                    audio.flatten().astype(np.float32), language="en"
                )["text"].strip()
                if text:
                    print(f"[VoiceAgent] Heard: {text}")
                    return text
            except Exception as e:
                print(f"[VoiceAgent] Whisper error: {e}")
        return self._text_input_fallback()

    # ── Intent Detection ───────────────────────────────────────────

    def _is_end_call_signal(self, text: str) -> bool:
        return any(p in text for p in ["goodbye", "bye", "hang up", "end call", "that's all", "i have to go"])

    def _detect_objection(self, text: str) -> Optional[str]:
        for kw in ["too expensive", "not interested", "no budget", "too busy",
                    "happy with current", "not now", "maybe later", "call me back",
                    "don't need", "waste of time", "not the right time"]:
            if kw in text:
                return kw
        return None

    def _detect_meeting_interest(self, user_input: str, agent_reply: str) -> bool:
        return any(p in user_input.lower() for p in [
            "book a meeting", "book a call", "schedule a meeting", "schedule a call",
            "set up a meeting", "set up a call", "let's do it", "let's schedule",
            "yes please book", "yes please schedule", "sign me up",
        ])

    def _detect_not_interested(self, text: str) -> bool:
        return any(p in text for p in [
            "not interested", "no thanks", "don't call me", "stop calling",
            "leave me alone", "take me off", "do not call", "unsubscribe",
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
        return ("Thank you for your time. I'll make sure to note your response. Have a great day!")

    # ── Call Result ────────────────────────────────────────────────

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
        }

    def stop(self):
        self.should_stop = True
        self.is_calling = False
