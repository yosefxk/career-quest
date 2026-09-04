import json
import logging
from typing import Dict, Any, Optional, List
import httpx
from app.core.config import settings

logger = logging.getLogger("career_quest.llm")

class LLMGateway:
    """
    Unified Multi-Provider AI Gateway.
    Supports: Google Gemini, OpenAI, Anthropic Claude, Groq, and local Ollama.
    """
    def __init__(self):
        self.provider = settings.AI_PROVIDER
        self.api_key = settings.AI_API_KEY
        self.model = settings.AI_MODEL

    def generate(self, prompt: str, system_prompt: Optional[str] = None, response_json: bool = False, timeout: float = 35.0) -> Optional[str]:
        if not self.api_key and self.provider != "ollama":
            logger.warning(f"No API Key configured for AI provider: {self.provider}")
            return None

        try:
            if self.provider == "gemini":
                return self._call_gemini(prompt, system_prompt, response_json, timeout)
            elif self.provider == "openai" or self.provider == "groq":
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
        if not self.api_key and self.provider != "ollama":
            logger.warning(f"No API Key configured for AI provider: {self.provider}")
            return "I am your CareerQuest AI Copilot. To enable live conversational intelligence, configure your AI API key in Settings or your .env file."

        try:
            if self.provider == "gemini":
                return self._chat_gemini(messages, system_prompt, timeout)
            elif self.provider == "openai" or self.provider == "groq":
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
            else:
                logger.error(f"Gemini API error {resp.status_code}: {resp.text}")
                return None

    def _call_openai_compatible(self, prompt: str, system_prompt: Optional[str], response_json: bool, timeout: float) -> Optional[str]:
        base_url = settings.GROQ_BASE_URL if self.provider == "groq" else settings.OPENAI_BASE_URL
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
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
            else:
                logger.error(f"Gemini Chat error {resp.status_code}: {resp.text}")
                return None

    def _chat_openai_compatible(self, messages: list, system_prompt: Optional[str], timeout: float) -> Optional[str]:
        base_url = settings.GROQ_BASE_URL if self.provider == "groq" else settings.OPENAI_BASE_URL
        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
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
