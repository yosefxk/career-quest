import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "CareerQuest"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Storage Directories
    DATA_DIR: str = os.getenv("DATA_DIR", "/app/data")
    CVS_DIR: str = os.getenv("CVS_DIR", "/app/data/CVs")
    DB_NAME: str = "career_quest.db"
    
    # AI Provider Settings
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "gemini").lower()  # gemini, openai, anthropic, groq, ollama
    AI_API_KEY: str = os.getenv("AI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    AI_MODEL: str = os.getenv("AI_MODEL", "gemini-3.7-flash")
    
    # Custom endpoints for local/proxy providers
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    ANTHROPIC_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    LOCAL_LLM_BASE_URL: str = os.getenv("LOCAL_LLM_BASE_URL", "http://host.docker.internal:1234/v1")
    
    # Optional Cloud & Local Backups
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", os.getenv("SMB_BACKUP_DIR", ""))

    @property
    def db_path(self) -> str:
        d = Path(self.DATA_DIR)
        d.mkdir(parents=True, exist_ok=True)
        return str(d / self.DB_NAME)

    @property
    def cvs_path(self) -> str:
        d = Path(self.CVS_DIR)
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

settings = Settings()
