import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.inference import runtime
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "models_dir", tmp_path / "models")
    monkeypatch.setattr(settings, "embedding_model", "")
    monkeypatch.setattr(settings, "launch_root", tmp_path / "data")
    from app.request_queue import scheduler
    assert not scheduler.items
    scheduler.paused = False
    runtime.model = None
    runtime.config = None
    runtime.error = None
    runtime.active.clear()
    with TestClient(app) as test:
        test.headers["X-Nelson-Client"] = "web"
        yield test
    runtime.model = None
    runtime.config = None


def sign_in(client, username="owner", password="correct-password-123"):
    result = client.post("/api/login", json={"username": username, "password": password})
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf"]
    return result.json()


@pytest.fixture
def admin(client):
    token = (settings.data_dir / "setup-token.txt").read_text()
    result = client.post("/api/setup", json={"username":"owner","password":"correct-password-123","setup_token":token})
    assert result.status_code == 201, result.text
    sign_in(client)
    return client


@pytest.fixture
def kb(admin):
    return admin.post("/api/knowledge", json={"name":"Training"}).json()["id"]
