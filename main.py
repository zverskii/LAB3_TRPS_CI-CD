from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4
from enum import Enum

app = FastAPI(
    title="CI/CD Platform API",
    version="1.0.0",
    description="REST API для управления сущностями CI/CD-платформы (FR-1, FR-2)",
)

# ---------- Enums ----------
class TriggerType(str, Enum):
    push = "push"
    merge_request = "merge_request"
    tag = "tag"
    cron = "cron"
    manual = "manual"

class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"

class ConfigFormat(str, Enum):
    yaml = "yaml"
    dsl = "dsl"

class TemplateScope(str, Enum):
    org = "org"
    project = "project"

# ---------- In-memory storage ----------
db = {
    "organizations": {},
    "projects": {},
    "repositories": {},
    "webhooks": {},
    "triggers": {},
    "configs": {},
    "config_versions": {},
    "templates": {},
    "runs": {},
}

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id() -> str:
    return str(uuid4())

# ---------- Schemas ----------
class OrganizationIn(BaseModel):
    name: str
    plan: str = "free"

class ProjectIn(BaseModel):
    org_id: str
    name: str
    visibility: str = "private"

class RepositoryIn(BaseModel):
    project_id: str
    provider: str          # github|gitlab|bitbucket
    url: str
    default_branch: str = "main"
    auth_secret_ref: Optional[str] = None

class WebhookIn(BaseModel):
    event_type: str        # push|mr|tag
    target_url: str
    secret: Optional[str] = None
    active: bool = True

class TriggerIn(BaseModel):
    type: TriggerType
    branch_filter: Optional[str] = None
    cron_expr: Optional[str] = None
    enabled: bool = True

class ConfigIn(BaseModel):
    path: str = ".ci/pipeline.yaml"
    format: ConfigFormat = ConfigFormat.yaml
    content: str

class ConfigVersionIn(BaseModel):
    commit_sha: str
    content: str

class TemplateIn(BaseModel):
    name: str
    body: str
    scope: TemplateScope = TemplateScope.project
    parent_template_id: Optional[str] = None
    project_id: Optional[str] = None

class RunIn(BaseModel):
    repository_id: str
    trigger_id: Optional[str] = None
    commit_sha: Optional[str] = None

# ================= ROUTES =================

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "time": now()}

# ---------- Organizations ----------
@app.post("/organizations", status_code=201, tags=["organizations"])
def create_org(body: OrganizationIn):
    oid = new_id()
    db["organizations"][oid] = {"id": oid, **body.model_dump(), "created_at": now()}
    return db["organizations"][oid]

@app.get("/organizations", tags=["organizations"])
def list_orgs():
    return list(db["organizations"].values())

@app.get("/organizations/{oid}", tags=["organizations"])
def get_org(oid: str):
    if oid not in db["organizations"]:
        raise HTTPException(404, "Organization not found")
    return db["organizations"][oid]

@app.delete("/organizations/{oid}", status_code=204, tags=["organizations"])
def delete_org(oid: str):
    db["organizations"].pop(oid, None)

# ---------- Projects ----------
@app.post("/projects", status_code=201, tags=["projects"])
def create_project(body: ProjectIn):
    if body.org_id not in db["organizations"]:
        raise HTTPException(400, "org_id does not exist")
    pid = new_id()
    db["projects"][pid] = {"id": pid, **body.model_dump(), "created_at": now()}
    return db["projects"][pid]

@app.get("/projects", tags=["projects"])
def list_projects():
    return list(db["projects"].values())

@app.get("/projects/{pid}", tags=["projects"])
def get_project(pid: str):
    if pid not in db["projects"]:
        raise HTTPException(404, "Project not found")
    return db["projects"][pid]

@app.delete("/projects/{pid}", status_code=204, tags=["projects"])
def delete_project(pid: str):
    db["projects"].pop(pid, None)

# ---------- Repositories (FR-1) ----------
@app.post("/repositories", status_code=201, tags=["repositories"])
def create_repo(body: RepositoryIn):
    if body.project_id not in db["projects"]:
        raise HTTPException(400, "project_id does not exist")
    rid = new_id()
    db["repositories"][rid] = {"id": rid, **body.model_dump(), "connected_at": now()}
    return db["repositories"][rid]

@app.get("/repositories", tags=["repositories"])
def list_repos():
    return list(db["repositories"].values())

@app.get("/repositories/{rid}", tags=["repositories"])
def get_repo(rid: str):
    if rid not in db["repositories"]:
        raise HTTPException(404, "Repository not found")
    return db["repositories"][rid]

@app.delete("/repositories/{rid}", status_code=204, tags=["repositories"])
def delete_repo(rid: str):
    db["repositories"].pop(rid, None)

# ---------- Webhooks (FR-1) ----------
@app.post("/repositories/{rid}/webhooks", status_code=201, tags=["webhooks"])
def create_webhook(rid: str, body: WebhookIn):
    if rid not in db["repositories"]:
        raise HTTPException(404, "Repository not found")
    wid = new_id()
    db["webhooks"][wid] = {"id": wid, "repo_id": rid, **body.model_dump(), "created_at": now()}
    return db["webhooks"][wid]

@app.get("/repositories/{rid}/webhooks", tags=["webhooks"])
def list_webhooks(rid: str):
    return [w for w in db["webhooks"].values() if w["repo_id"] == rid]

@app.delete("/webhooks/{wid}", status_code=204, tags=["webhooks"])
def delete_webhook(wid: str):
    db["webhooks"].pop(wid, None)

# ---------- Triggers (FR-1) ----------
@app.post("/repositories/{rid}/triggers", status_code=201, tags=["triggers"])
def create_trigger(rid: str, body: TriggerIn):
    if rid not in db["repositories"]:
        raise HTTPException(404, "Repository not found")
    if body.type == TriggerType.cron and not body.cron_expr:
        raise HTTPException(400, "cron_expr is required for cron trigger")
    tid = new_id()
    db["triggers"][tid] = {"id": tid, "repo_id": rid, **body.model_dump(), "created_at": now()}
    return db["triggers"][tid]

@app.get("/repositories/{rid}/triggers", tags=["triggers"])
def list_triggers(rid: str):
    return [t for t in db["triggers"].values() if t["repo_id"] == rid]

@app.patch("/triggers/{tid}", tags=["triggers"])
def update_trigger(tid: str, body: dict):
    if tid not in db["triggers"]:
        raise HTTPException(404, "Trigger not found")
    db["triggers"][tid].update(body)
    return db["triggers"][tid]

@app.delete("/triggers/{tid}", status_code=204, tags=["triggers"])
def delete_trigger(tid: str):
    db["triggers"].pop(tid, None)

# ---------- PipelineConfigs + Versions (FR-2) ----------
@app.post("/repositories/{rid}/configs", status_code=201, tags=["configs"])
def create_config(rid: str, body: ConfigIn):
    if rid not in db["repositories"]:
        raise HTTPException(404, "Repository not found")
    cid = new_id()
    db["configs"][cid] = {
        "id": cid, "repo_id": rid,
        "path": body.path, "format": body.format.value,
        "created_at": now(),
    }
    vid = new_id()
    db["config_versions"][vid] = {
        "id": vid, "config_id": cid,
        "commit_sha": "initial",
        "content": body.content,
        "is_valid": True,
        "created_at": now(),
    }
    return {**db["configs"][cid], "version_id": vid}

@app.get("/repositories/{rid}/configs", tags=["configs"])
def list_configs(rid: str):
    return [c for c in db["configs"].values() if c["repo_id"] == rid]

@app.get("/configs/{cid}", tags=["configs"])
def get_config(cid: str):
    if cid not in db["configs"]:
        raise HTTPException(404, "Config not found")
    return db["configs"][cid]

@app.post("/configs/{cid}/versions", status_code=201, tags=["configs"])
def add_version(cid: str, body: ConfigVersionIn):
    if cid not in db["configs"]:
        raise HTTPException(404, "Config not found")
    vid = new_id()
    db["config_versions"][vid] = {
        "id": vid, "config_id": cid,
        "commit_sha": body.commit_sha,
        "content": body.content,
        "is_valid": True,
        "created_at": now(),
    }
    return db["config_versions"][vid]

@app.get("/configs/{cid}/versions", tags=["configs"])
def list_versions(cid: str):
    return [v for v in db["config_versions"].values() if v["config_id"] == cid]

@app.get("/configs/{cid}/versions/{vid}", tags=["configs"])
def get_version(cid: str, vid: str):
    v = db["config_versions"].get(vid)
    if not v or v["config_id"] != cid:
        raise HTTPException(404, "Version not found")
    return v

# ---------- Templates (FR-2) ----------
@app.post("/templates", status_code=201, tags=["templates"])
def create_template(body: TemplateIn):
    if body.parent_template_id and body.parent_template_id not in db["templates"]:
        raise HTTPException(400, "parent_template_id does not exist")
    tid = new_id()
    db["templates"][tid] = {"id": tid, **body.model_dump(), "created_at": now()}
    return db["templates"][tid]

@app.get("/templates", tags=["templates"])
def list_templates():
    return list(db["templates"].values())

@app.get("/templates/{tid}", tags=["templates"])
def get_template(tid: str):
    if tid not in db["templates"]:
        raise HTTPException(404, "Template not found")
    return db["templates"][tid]

# ---------- PipelineRuns ----------
@app.post("/runs", status_code=201, tags=["runs"])
def create_run(body: RunIn):
    if body.repository_id not in db["repositories"]:
        raise HTTPException(404, "Repository not found")
    run_id = new_id()
    db["runs"][run_id] = {
        "id": run_id,
        "repository_id": body.repository_id,
        "trigger_id": body.trigger_id,
        "commit_sha": body.commit_sha,
        "status": RunStatus.running.value,
        "started_at": now(),
        "finished_at": None,
    }
    return db["runs"][run_id]

@app.get("/runs", tags=["runs"])
def list_runs():
    return list(db["runs"].values())

@app.get("/runs/{run_id}", tags=["runs"])
def get_run(run_id: str):
    if run_id not in db["runs"]:
        raise HTTPException(404, "Run not found")
    return db["runs"][run_id]

@app.post("/runs/{run_id}/cancel", tags=["runs"])
def cancel_run(run_id: str):
    if run_id not in db["runs"]:
        raise HTTPException(404, "Run not found")
    db["runs"][run_id]["status"] = RunStatus.cancelled.value
    db["runs"][run_id]["finished_at"] = now()
    return db["runs"][run_id]