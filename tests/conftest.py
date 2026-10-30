import os
import sys
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway database before anything imports the settings.
_TMP = Path(tempfile.mkdtemp(prefix="bharosa-test-"))
os.environ["DB_PATH"] = str(_TMP / "test.db")
os.environ["LLM_MODE"] = "template"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def fresh(client):
    """Reset the world before a test that mutates state."""
    r = client.post("/api/demo/reset")
    assert r.status_code == 200
    return client
