import pytest
import os
import tempfile
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
backend_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_path))

# Configure temporary test storage directory
temp_data_dir = tempfile.mkdtemp(prefix="cq_test_data_")
temp_cvs_dir = os.path.join(temp_data_dir, "CVs")
os.makedirs(temp_cvs_dir, exist_ok=True)

os.environ["DATA_DIR"] = temp_data_dir
os.environ["CVS_DIR"] = temp_cvs_dir
os.environ["AI_PROVIDER"] = "ollama"  # Uses mock / local fallback in tests
os.environ["AI_API_KEY"] = "test_key"

from app.core.database import init_db
from app.main import app
from fastapi.testclient import TestClient

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()
    yield

@pytest.fixture
def client():
    return TestClient(app)
