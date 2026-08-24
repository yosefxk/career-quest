# Contributing to CareerQuest ⚡

Thank you for your interest in contributing to CareerQuest! We welcome community contributions, bug fixes, feature proposals, and documentation improvements.

---

## 🛠️ Development Workflow

1. **Fork the Repository**:
   Create a fork on GitHub and clone your fork locally:
   ```bash
   git clone https://github.com/<your-username>/career-quest.git
   cd career-quest
   ```

2. **Set Up Local Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   make install
   ```

3. **Create a Feature Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Run Tests Locally**:
   Ensure all tests pass before opening a pull request:
   ```bash
   make test
   ```

5. **Submit a Pull Request**:
   Push your branch and open a PR against `main`. Ensure your PR description clearly outlines the problem solved and changes made.

---

## 📐 Architecture Principles

* **Decoupled Identity**: Never hardcode personal attributes or candidate specifics into core models or engines.
* **Pluggable LLM Gateway**: All AI calls must route through `llm_gateway.py` with structured JSON schema outputs.
* **Strict Single-Page ATS Fit**: Any resume rendering template adjustments must strictly adhere to the 1-page line budget.
