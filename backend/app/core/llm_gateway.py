import json
import logging
from typing import Dict, Any, Optional, List
import httpx
from app.core.config import settings

logger = logging.getLogger("career_quest.llm")

DEFAULT_MODELS = {
    "gemini": "gemini-3.7-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-20241022",
    "groq": "llama-3.3-70b-versatile",
    "ollama": "llama3.1",
    "local": "local-model",
    "lmstudio": "local-model",
    "vllm": "local-model",
    "localai": "local-model"
}

LOCAL_PROVIDERS = {"ollama", "local", "lmstudio", "vllm", "localai"}

class LLMGateway:
    """
    Unified Multi-Provider AI Gateway.
    Supports: Google Gemini, OpenAI, Anthropic Claude, Groq, local Ollama,
    and any local OpenAI-compatible server (LM Studio, vLLM, LocalAI).
    """
    def __init__(self):
        import os
        self.provider = settings.AI_PROVIDER
        self.api_key = settings.AI_API_KEY
        explicit_model = os.getenv("AI_MODEL")
        if explicit_model:
            self.model = explicit_model
        elif self.provider == "gemini" and os.getenv("GEMINI_MODEL"):
            self.model = os.getenv("GEMINI_MODEL")
        else:
            self.model = DEFAULT_MODELS.get(self.provider, settings.AI_MODEL)

    def _is_local_provider(self) -> bool:
        return self.provider in LOCAL_PROVIDERS

    def _get_openai_compatible_base_url(self) -> str:
        if self.provider == "groq":
            return settings.GROQ_BASE_URL
        if self.provider in ["local", "lmstudio", "vllm", "localai"]:
            return settings.LOCAL_LLM_BASE_URL or settings.OPENAI_BASE_URL
        return settings.OPENAI_BASE_URL

    def generate(self, prompt: str, system_prompt: Optional[str] = None, response_json: bool = False, timeout: float = 35.0) -> Optional[str]:
        if not self.api_key and not self._is_local_provider():
            logger.warning(f"No API Key configured for AI provider: {self.provider}")
            return None

        try:
            if self.provider == "gemini":
                return self._call_gemini(prompt, system_prompt, response_json, timeout)
            elif self.provider in ["openai", "groq", "local", "lmstudio", "vllm", "localai"]:
                return self._call_openai_compatible(prompt, system_prompt, response_json, timeout)
            elif self.provider == "anthropic":
                return self._call_anthropic(prompt, system_prompt, response_json, timeout)
            elif self.provider == "ollama":
                return self._call_ollama(prompt, system_prompt, response_json, timeout)
            else:
                logger.error(f"Unsupported AI provider: {self.provider}")
                return None
        except Exception as e:
            logger.error(f"LLM Gateway Error [{self.provider}]: {e}")
            return None

    def chat(self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None, timeout: float = 45.0) -> Optional[str]:
        if not self.api_key and not self._is_local_provider():
            logger.warning(f"No API Key configured for AI provider: {self.provider}")
            return "I am your CareerQuest Career Coach. To enable live conversational intelligence, configure your AI API key in Settings or your .env file."

        try:
            if self.provider == "gemini":
                return self._chat_gemini(messages, system_prompt, timeout)
            elif self.provider in ["openai", "groq", "local", "lmstudio", "vllm", "localai"]:
                return self._chat_openai_compatible(messages, system_prompt, timeout)
            elif self.provider == "anthropic":
                return self._chat_anthropic(messages, system_prompt, timeout)
            elif self.provider == "ollama":
                return self._chat_ollama(messages, system_prompt, timeout)
            else:
                logger.error(f"Unsupported AI provider: {self.provider}")
                return None
        except Exception as e:
            logger.error(f"LLM Gateway Chat Error [{self.provider}]: {e}")
            return None

    def _call_gemini(self, prompt: str, system_prompt: Optional[str], response_json: bool, timeout: float) -> Optional[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self.api_key
        }
        
        full_text = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        payload = {
            "contents": [{"parts": [{"text": full_text}]}]
        }
        if response_json:
            payload["generationConfig"] = {"responseMimeType": "application/json"}

        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            elif resp.status_code in [429, 503] and self.model != "gemini-3.6-flash":
                logger.warning(f"Gemini {self.model} returned {resp.status_code}. Retrying with gemini-3.6-flash...")
                fallback_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
                resp2 = client.post(fallback_url, headers=headers, json=payload)
                if resp2.status_code == 200:
                    return resp2.json()["candidates"][0]["content"]["parts"][0]["text"]
                logger.error(f"Gemini Fallback error {resp2.status_code}: {resp2.text}")
                return None
            else:
                logger.error(f"Gemini API error {resp.status_code}: {resp.text}")
                return None

    def _call_openai_compatible(self, prompt: str, system_prompt: Optional[str], response_json: bool, timeout: float) -> Optional[str]:
        base_url = self._get_openai_compatible_base_url()
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self._is_local_provider():
            headers["Authorization"] = "Bearer dummy"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2
        }
        if response_json:
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                logger.error(f"{self.provider} API error {resp.status_code}: {resp.text}")
                return None

    def _call_anthropic(self, prompt: str, system_prompt: Optional[str], response_json: bool, timeout: float) -> Optional[str]:
        url = f"{settings.ANTHROPIC_BASE_URL}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}]
        }
        if system_prompt:
            payload["system"] = system_prompt

        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"]
            else:
                logger.error(f"Anthropic API error {resp.status_code}: {resp.text}")
                return None

    def _call_ollama(self, prompt: str, system_prompt: Optional[str], response_json: bool, timeout: float) -> Optional[str]:
        url = f"{settings.OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": self.model or "llama3.1",
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False
        }
        if response_json:
            payload["format"] = "json"

        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.json().get("response")
            else:
                logger.error(f"Ollama API error {resp.status_code}: {resp.text}")
                return None

    def generate_json(self, prompt: str, system_prompt: Optional[str] = None, timeout: float = 35.0) -> Optional[Dict[str, Any]]:
        raw = self.generate(prompt, system_prompt, response_json=True, timeout=timeout)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            # Fallback regex extraction if model enclosed JSON in codeblocks
            import re
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
        return None

    def _chat_gemini(self, messages: list, system_prompt: Optional[str], timeout: float) -> Optional[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self.api_key
        }
        contents = []
        for m in messages:
            role = "user" if m.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
            
        payload = {"contents": contents}
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
            
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            elif resp.status_code in [429, 503] and self.model != "gemini-3.6-flash":
                logger.warning(f"Gemini {self.model} returned {resp.status_code}. Retrying with gemini-3.6-flash...")
                fallback_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
                resp2 = client.post(fallback_url, headers=headers, json=payload)
                if resp2.status_code == 200:
                    return resp2.json()["candidates"][0]["content"]["parts"][0]["text"]
                logger.error(f"Gemini Fallback chat error {resp2.status_code}: {resp2.text}")
                return None
            else:
                logger.error(f"Gemini Chat error {resp.status_code}: {resp.text}")
                return None

    def _chat_openai_compatible(self, messages: list, system_prompt: Optional[str], timeout: float) -> Optional[str]:
        base_url = self._get_openai_compatible_base_url()
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self._is_local_provider():
            headers["Authorization"] = "Bearer dummy"
        formatted = []
        if system_prompt:
            formatted.append({"role": "system", "content": system_prompt})
        for m in messages:
            formatted.append({"role": m.get("role", "user"), "content": m.get("content", "")})
            
        payload = {
            "model": self.model,
            "messages": formatted,
            "temperature": 0.4
        }
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                logger.error(f"{self.provider} Chat error {resp.status_code}: {resp.text}")
                return None

    def _chat_anthropic(self, messages: list, system_prompt: Optional[str], timeout: float) -> Optional[str]:
        url = f"{settings.ANTHROPIC_BASE_URL}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": formatted
        }
        if system_prompt:
            payload["system"] = system_prompt
            
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"]
            else:
                logger.error(f"Anthropic Chat error {resp.status_code}: {resp.text}")
                return None

    def _chat_ollama(self, messages: list, system_prompt: Optional[str], timeout: float) -> Optional[str]:
        url = f"{settings.OLLAMA_BASE_URL}/api/chat"
        formatted = []
        if system_prompt:
            formatted.append({"role": "system", "content": system_prompt})
        for m in messages:
            formatted.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        payload = {
            "model": self.model or "llama3.1",
            "messages": formatted,
            "stream": False
        }
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.json().get("message", {}).get("content")
            else:
                logger.error(f"Ollama Chat error {resp.status_code}: {resp.text}")
                return None

llm = LLMGateway()
