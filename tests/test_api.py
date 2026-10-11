"""
Базовые тесты REST API CI/CD-платформы.
Проверяют сквозной сценарий: Organization → Project → Repository → Trigger → Config → Run.
"""
import pytest
from fastapi.testclient import TestClient
from main import app, db

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    """Очищаем in-memory хранилище перед каждым тестом."""
    for key in db:
        db[key].clear()
    yield


# ---------- Health ----------
def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------- Organizations ----------
def test_create_and_get_organization():
    r = client.post("/organizations", json={"name": "Acme", "plan": "pro"})
    assert r.status_code == 201
    oid = r.json()["id"]

    r = client.get(f"/organizations/{oid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Acme"

    r = client.get("/organizations/unknown")
    assert r.status_code == 404


# ---------- Full E2E ----------
def test_full_cicd_flow():
    # 1. Организация
    org = client.post("/organizations", json={"name": "Acme"}).json()

    # 2. Проект
    prj = client.post("/projects", json={
        "org_id": org["id"], "name": "backend"
    }).json()

    # 3. Репозиторий
    repo = client.post("/repositories", json={
        "project_id": prj["id"],
        "provider": "github",
        "url": "https://github.com/acme/backend",
    }).json()

    # 4. Триггер push
    trig = client.post(f"/repositories/{repo['id']}/triggers", json={
        "type": "push", "branch_filter": "main",
    }).json()
    assert trig["type"] == "push"

    # 5. Конфигурация пайплайна
    cfg = client.post(f"/repositories/{repo['id']}/configs", json={
        "path": ".ci/pipeline.yaml",
        "format": "yaml",
        "content": "stages:\n  - build\n  - test",
    }).json()
    assert "version_id" in cfg

    # 6. Запуск пайплайна
    run = client.post("/runs", json={
        "repository_id": repo["id"],
        "trigger_id": trig["id"],
        "commit_sha": "abc123",
    }).json()
    assert run["status"] == "running"

    # 7. Отмена
    cancelled = client.post(f"/runs/{run['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"


# ---------- Негативные проверки ----------
def test_cron_trigger_requires_cron_expr():
    org = client.post("/organizations", json={"name": "Acme"}).json()
    prj = client.post("/projects", json={
        "org_id": org["id"], "name": "backend"
    }).json()
    repo = client.post("/repositories", json={
        "project_id": prj["id"], "provider": "github",
        "url": "https://github.com/acme/backend",
    }).json()

    r = client.post(f"/repositories/{repo['id']}/triggers",
                    json={"type": "cron"})
    assert r.status_code == 400


def test_run_on_unknown_repo_returns_404():
    r = client.post("/runs", json={"repository_id": "no-such-id"})
    assert r.status_code == 404