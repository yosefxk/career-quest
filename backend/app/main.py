import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.core.llm_gateway import llm
from app.routers import profile, jobs, digest, tailor, ats, intel, copilot

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Modular Routers
app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(digest.router)
app.include_router(tailor.router)
app.include_router(ats.router)
app.include_router(intel.router)
app.include_router(copilot.router)

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "ai_provider": settings.AI_PROVIDER,
        "ai_model": settings.AI_MODEL
    }

@app.get("/api/v1/system/status")
def system_status():
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "ai_provider": settings.AI_PROVIDER,
        "ai_model": settings.AI_MODEL,
        "has_api_key": bool(settings.AI_API_KEY) or settings.AI_PROVIDER == "ollama",
        "data_dir": settings.DATA_DIR,
        "cvs_dir": settings.CVS_DIR,
        "backup_dir": settings.BACKUP_DIR,
        "backup_active": bool(settings.BACKUP_DIR)
    }

# Mount Frontend Static Assets
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend_dir.exists():
    @app.get("/", response_class=HTMLResponse)
    def serve_index():
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return HTMLResponse("<h1>CareerQuest Backend Running</h1><p>Frontend index.html not found.</p>")

    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
