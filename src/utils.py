import os
import yaml
from pathlib import Path
from typing import Any

import dotenv

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def _load_yaml(filename: str) -> dict:
    path = CONFIG_DIR / filename
    if not path.exists():
        print(f"[Utils] Warning: {path} not found, returning empty config")
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_settings() -> dict:
    return _load_yaml("settings.yaml")


def load_prompts() -> dict:
    return _load_yaml("prompts.yaml")


def load_knowledge_base() -> dict:
    return _load_yaml("knowledge_base.yaml")


def load_env():
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        dotenv.load_dotenv(env_path)
        print(f"[Utils] Loaded environment from {env_path}")
    else:
        print(f"[Utils] No .env file found at {env_path}")


def get_llm_client():
    load_env()
    settings = load_settings()
    provider = settings["llm"]["provider"]

    if provider == "ollama":
        from openai import OpenAI
        base_url = settings["llm"]["ollama"]["base_url"]
        model = settings["llm"]["ollama"]["model"]
        print(f"[Utils] Using Ollama LLM: {model} @ {base_url}")
        return OpenAI(base_url=f"{base_url}/v1", api_key="ollama")

    else:
        from openai import OpenAI
        base_url = settings["llm"].get("base_url", "")
        api_key_env = settings["llm"].get("api_key_env_var", "OPENAI_API_KEY")
        api_key = os.getenv(api_key_env) or os.getenv("OPENAI_API_KEY")

        if not api_key:
            print(f"[Utils] WARNING: {api_key_env} not set. LLM calls will fail.")
            print("[Utils] Set it in .env or use a different provider.")
            api_key = "sk-placeholder"

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        model = settings["llm"]["model"]
        print(f"[Utils] Using LLM: {model} @ {base_url or 'api.openai.com'}")
        return OpenAI(**client_kwargs)
