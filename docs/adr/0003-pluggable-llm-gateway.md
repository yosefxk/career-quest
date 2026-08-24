# ADR 0003: Pluggable Multi-Provider LLM Gateway with Structured JSON Validation

## Status
Accepted

## Context
AI resume tailoring, role parsing, and mock interview synthesis should not be locked into a single AI provider. Users may want to utilize Google Gemini, OpenAI GPT-4o, Anthropic Claude, Groq for high speed, or local Ollama for 100% private, offline air-gapped environments.

## Decision
We implemented a unified `LLMGateway` abstraction in `app/core/llm_gateway.py` with deterministic JSON extraction, retry fallbacks, and regex schema parsing.

## Consequences
### Positive
* **Zero Vendor Lock-in**: Users can switch AI models with a single environment variable change (`AI_PROVIDER=ollama` or `AI_PROVIDER=openai`).
* **Offline Privacy**: Complete support for local Ollama endpoints prevents sensitive career data from leaving the user's private network.
* **Resilience**: Unified error handling and schema extraction across all API response shapes.

### Negative
* Requires maintaining API payload format adapters across distinct provider endpoints.
