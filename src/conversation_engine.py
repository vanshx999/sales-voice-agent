import time
import yaml
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from openai import APIError, APIConnectionError, APITimeoutError, RateLimitError

from .utils import load_settings, load_prompts, load_knowledge_base, get_llm_client

CONFIG_DIR = Path(__file__).parent.parent / "config"


class ConversationEngine:
    def __init__(self):
        self.settings = load_settings()
        self.prompts = load_prompts()
        self.kb = load_knowledge_base()
        self.llm = get_llm_client()
        self.model = self.settings["llm"]["model"]
        self.temperature = self.settings["llm"]["temperature"]
        self.max_tokens = self.settings["llm"]["max_tokens"]
        self.conversation_history: list[dict] = []
        self.lead_info: dict = {}

    def start_call(self, lead):
        self.conversation_history = []
        self.lead_info = {
            "name": lead.name,
            "company": lead.company,
            "lead_id": lead.id,
            "phone": lead.phone,
        }

    def _build_system_prompt(self) -> str:
        return self.prompts["system_prompt"].format(
            company_name=self.kb["company"]["name"],
            agent_name=self.kb["company"]["agent_name"],
            company_description=self.kb["company"]["description"],
        )

    def _build_context(self) -> str:
        return f"""
Company: {self.kb['company']['name']}
Products: {json.dumps(self.kb['company']['products'], indent=2)}
Use Cases: {json.dumps(self.kb['company']['use_cases'], indent=2)}
Common Questions: {json.dumps(self.kb['company']['common_questions'], indent=2)}
Value Propositions: {json.dumps(self.kb['company']['value_propositions'], indent=2)}
"""

    def generate_greeting(self) -> str:
        prompt = self.prompts["greeting_prompt"].format(
            company_name=self.kb["company"]["name"],
            agent_name=self.kb["company"]["agent_name"],
            lead_name=self.lead_info["name"],
            lead_company=self.lead_info["company"],
            call_reason="introduce our workflow automation solutions",
        )
        greeting = self._llm_generate(prompt, max_tokens=60)
        greeting = greeting.strip("\"' ")
        self.conversation_history.append({"role": "assistant", "content": greeting})
        return greeting

    def _llm_call(self, messages: list[dict], max_tokens: int, retries: int = 3) -> str:
        for attempt in range(retries):
            try:
                response = self.llm.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content.strip()
            except (APITimeoutError, APIConnectionError, RateLimitError, APIError) as e:
                print(f"[ConversationEngine] LLM error (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(3 * (attempt + 1))
                else:
                    print("[ConversationEngine] All retries failed, using fallback")
                    return self._fallback_response(messages)
            except Exception as e:
                print(f"[ConversationEngine] Unexpected LLM error: {e}")
                return self._fallback_response(messages)

    def _fallback_response(self, messages: list[dict]) -> str:
        fallbacks = [
            "That's interesting. Could you tell me a bit more about your situation?",
            "I understand. What would solving this problem mean for your business?",
            "That makes sense. How are you currently handling that process?",
            "I see. What's your timeline for making a change?",
            "Thank you for sharing that. What would an ideal solution look like for you?",
        ]
        idx = len(self.conversation_history) // 2 % len(fallbacks)
        return fallbacks[idx]

    def process_input(self, user_input: str) -> str:
        self.conversation_history.append({"role": "user", "content": user_input})

        messages = [
            {"role": "system", "content": self._build_system_prompt() + "\n\n## CONTEXT\n" + self._build_context()},
            *self._build_recent_history(),
        ]

        reply = self._llm_call(messages, self.max_tokens)
        self.conversation_history.append({"role": "assistant", "content": reply})
        return reply

    def _build_recent_history(self, max_turns: int = 10) -> list[dict]:
        return self.conversation_history[-max_turns:]

    def _llm_generate(self, prompt: str, max_tokens: int = 100) -> str:
        return self._llm_call(
            [{"role": "user", "content": prompt}], max_tokens,
        )

    def qualify_lead(self) -> dict:
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in self.conversation_history
        )
        prompt = self.prompts["qualification_prompt"].format(
            conversation_history=history_text
        )
        result = self._llm_generate(prompt, max_tokens=300)

        defaults = {
            "qualified": "maybe", "budget": "unknown", "authority": "unknown",
            "need": "unknown", "timeline": "unknown",
            "requirements": [], "pain_points": [],
        }

        try:
            parsed = json.loads(self._extract_json(result))
            for k in defaults:
                if k in parsed:
                    defaults[k] = parsed[k]
        except Exception:
            pass

        return defaults

    def handle_objection(self, objection: str) -> str:
        prompt = self.prompts["objection_response_prompt"].format(
            objection=objection,
            company_info=self._build_context(),
            prospect_context=json.dumps(self.lead_info),
        )
        response = self._llm_generate(prompt, max_tokens=80)
        self.conversation_history.append({"role": "assistant", "content": response})
        return response

    def generate_summary(self) -> dict:
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in self.conversation_history[-20:]
        )
        prompt = self.prompts["summary_prompt"].format(
            conversation_history=history_text
        )
        result = self._llm_generate(prompt, max_tokens=300)

        defaults = {
            "outcome": "unknown", "summary": "", "requirements": "",
            "objections": "", "next_steps": "", "follow_up": "",
            "meeting_date": "",
        }

        try:
            parsed = json.loads(self._extract_json(result))
            for k in defaults:
                if k in parsed:
                    defaults[k] = parsed[k]
        except Exception:
            pass

        return defaults

    def _extract_json(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]
        return text
