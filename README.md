# CareerQuest ⚡

**CareerQuest** is a modern, self-hostable AI Career Intelligence, Multi-Platform Job Discovery, and ATS Resume Tailor Studio.

Built for candidates who want to run high-speed parallel discovery scans across top tech company job boards, dynamically tailor single-page ATS-optimized resumes with an interactive bullet bank, generate customized recruiter outreach, and practice role-specific technical & STAR mock interviews.

---

## Key Features

1. **Candidate Master Profile & AI Resume Onboarding**:
   - Upload any existing resume (PDF, TXT, MD, YAML) to automatically parse full contact registry, experience, education, skills, and archetypes with AI.
   - Built to support any candidate, avoiding hardcoded personal details.
2. **Multi-Platform Parallel Discovery Scraper**:
   - Parallel scraping across **Greenhouse** and **Ashby** portals (Waymo, Anduril, OpenAI, Anthropic, Scale AI, Databricks, Cloudflare, Wiz, Stripe, Ramp, Linear, Figma, etc.).
   - Live SSE progress stream with deduplication and compensation estimation.
3. **Interactive Bullet Bank (Strict 1-Page Baseline)**:
   - Interactive bullet bank with category filtering and live budget counter ensuring strict 1-page PDF formatting.
4. **ATS Compliance Inspector & Side-by-Side Diff**:
   - Real-time ATS parsing score (0–100%), text-layer verification, heading compliance, keyword density audit, and visual diff vs. Master Profile baseline.
5. **Multi-Provider AI Gateway**:
   - Pluggable support for **Google Gemini**, **OpenAI**, **Anthropic Claude**, **Groq**, and local **Ollama** for 100% offline privacy.
6. **Portainer & Docker Ready**:
   - Single lightweight container with persistent SQLite storage and zero cloud lock-in.

---

## 🚀 Quickstart (Docker & Portainer)

### 1. Run with Docker Compose
```bash
cp .env.example .env
# Edit your AI_API_KEY in .env
docker compose up -d --build
```
Open **`http://localhost:8099`** in your browser.

### 2. Deploy as a Portainer Stack
1. Open Portainer &rarr; **Stacks** &rarr; **Add stack**.
2. Paste the contents of [`docker-compose.yml`](docker-compose.yml).
3. Add environment variables:
   - `AI_PROVIDER`: `gemini` (or `openai`, `anthropic`, `ollama`)
   - `AI_API_KEY`: Your API key
   - `PORT`: `8099`
4. Click **Deploy the stack**.

---

## 🛠️ Tech Stack
- **Backend**: FastAPI (Python 3.11/3.12), Pydantic v2, SQLite WAL mode, Playwright Chromium, PyPDF.
- **Frontend**: Responsive Single-Page Application (Tailwind CSS, Alpine.js, FontAwesome 6).
- **AI Gateway**: Multi-model unified client with JSON schema enforcement.
