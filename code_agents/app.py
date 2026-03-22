import importlib.metadata
import logging
import os
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import backend as _backend_mod
from .config import agent_loader
from .logging_config import setup_logging
from .openai_errors import openai_style_error, process_error_json_response, unwrap_process_error
from .routers import completions, agents_list, redash, elasticsearch as elasticsearch_router, atlassian_oauth_web
from .routers import git_ops as git_ops_router, testing as testing_router
from .routers import jenkins as jenkins_router
from .routers import argocd as argocd_router
from .routers import pipeline as pipeline_router
from .public_urls import atlassian_cloud_site_url, code_agents_public_base_url

logger = logging.getLogger("code_agents.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure logging is configured even when started via `uvicorn code_agents.app:app` (skips main.py).
    setup_logging()

    # Load env: global config + per-repo overrides before agent YAML expands ${CURSOR_API_KEY} / etc.
    from .env_loader import load_all_env
    load_all_env()
    logger.info("=" * 60)
    logger.info("CODE AGENTS SERVER STARTING")
    logger.info("=" * 60)
    logger.info("PID=%d, Python=%s, cwd=%s", os.getpid(), sys.version.split()[0], os.getcwd())

    agent_loader.load()
    agents = agent_loader.list_agents()
    logger.info("Loaded %d agent(s):", len(agents))
    for a in agents:
        logger.info(
            "  %-25s backend=%-8s model=%-16s permission=%s cwd=%s",
            a.name, a.backend, a.model, a.permission_mode, a.cwd,
        )

    # Log environment configuration (no secrets)
    logger.info("Environment: LOG_LEVEL=%s, HOST=%s, PORT=%s",
                os.getenv("LOG_LEVEL", "INFO"), os.getenv("HOST", "0.0.0.0"), os.getenv("PORT", "8000"))
    logger.info("Environment: CURSOR_API_URL=%s, CODE_AGENTS_HTTP_ONLY=%s",
                "set" if os.getenv("CURSOR_API_URL", "").strip() else "unset",
                os.getenv("CODE_AGENTS_HTTP_ONLY", "unset"))
    logger.info("Environment: TARGET_REPO_PATH=%s", os.getenv("TARGET_REPO_PATH", "(not set, will use cwd)"))
    logger.info("Environment: JENKINS_URL=%s", "set" if os.getenv("JENKINS_URL", "").strip() else "unset")
    logger.info("Environment: ARGOCD_URL=%s", "set" if os.getenv("ARGOCD_URL", "").strip() else "unset")

    if not os.getenv("CURSOR_API_URL", "").strip() and any(
        getattr(a, "backend", "") == "cursor" for a in agents
    ):
        logger.warning(
            "cursor agents use the cursor-agent CLI. Without the Cursor desktop app, "
            "set CURSOR_API_URL in .env for HTTP mode (see README), or expect 502 / ProcessError."
        )
    logger.info("=" * 60)
    logger.info("SERVER READY — accepting requests")
    logger.info("=" * 60)
    yield
    logger.info("CODE AGENTS SERVER SHUTTING DOWN (PID=%d)", os.getpid())


app = FastAPI(title="Code Agents API", lifespan=lifespan)

try:
    from cursor_agent_sdk._errors import ProcessError as _CursorProcessError
except ImportError:
    _CursorProcessError = None  # type: ignore[misc,assignment]

if _CursorProcessError is not None:

    @app.exception_handler(_CursorProcessError)
    async def cursor_process_error_handler(_request: Request, exc: _CursorProcessError):
        """Fallback when ProcessError is not caught in the router (e.g. other code paths)."""
        return process_error_json_response(exc)


if sys.version_info >= (3, 11):
    from builtins import ExceptionGroup as _ExceptionGroup

    @app.exception_handler(_ExceptionGroup)
    async def exception_group_handler(_request: Request, exc: _ExceptionGroup):
        """Starlette may wrap a single ProcessError in ExceptionGroup (TaskGroup); unwrap for 502 JSON."""
        pe = unwrap_process_error(exc)
        if pe is not None:
            return process_error_json_response(pe)
        return JSONResponse(
            status_code=500,
            content=openai_style_error(
                str(exc),
                error_type="internal_error",
                code="exception_group",
            ),
        )


@app.exception_handler(Exception)
async def json_exception_handler(request: Request, exc: Exception):
    """Return JSON errors so OpenAI-compatible clients (e.g. Open WebUI) get application/json, not text/plain."""
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=openai_style_error(str(exc.detail), error_type="invalid_request_error", code="http_error"),
        )
    pe = unwrap_process_error(exc)
    if pe is not None:
        return process_error_json_response(pe)
    return JSONResponse(
        status_code=500,
        content=openai_style_error(str(exc), error_type="internal_error", code="server_error"),
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request with method, path, status, duration, and client info."""
    start = time.monotonic()
    client_ip = request.client.host if request.client else "unknown"
    query = str(request.url.query) if request.url.query else ""
    path = request.url.path

    # Log request arrival
    if path not in ("/health", "/favicon.ico"):
        logger.info(
            "→ %s %s%s client=%s content-type=%s",
            request.method, path,
            f"?{query}" if query else "",
            client_ip,
            request.headers.get("content-type", "-"),
        )

    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000

    # Log response
    if path in ("/health", "/favicon.ico"):
        logger.debug("← %s %s → %d (%.1fms)", request.method, path, response.status_code, duration_ms)
    elif response.status_code >= 500:
        logger.error(
            "← %s %s → %d (%.1fms) client=%s",
            request.method, path, response.status_code, duration_ms, client_ip,
        )
    elif response.status_code >= 400:
        logger.warning(
            "← %s %s → %d (%.1fms) client=%s",
            request.method, path, response.status_code, duration_ms, client_ip,
        )
    else:
        logger.info("← %s %s → %d (%.1fms)", request.method, path, response.status_code, duration_ms)

    return response


app.include_router(completions.router)
app.include_router(agents_list.router)
app.include_router(redash.router)
app.include_router(elasticsearch_router.router)

# Atlassian OAuth (same origin as Open WebUI: CODE_AGENTS_PUBLIC_BASE_URL/v1)
if os.getenv("ATLASSIAN_OAUTH_CLIENT_ID", "").strip():
    app.include_router(atlassian_oauth_web.router)

# Git operations + testing (always registered — repo_path can be passed per-request or defaults to cwd)
app.include_router(git_ops_router.router)
app.include_router(testing_router.router)

# Jenkins CI/CD (requires JENKINS_URL for actual API calls, but router is always available)
app.include_router(jenkins_router.router)

# ArgoCD (requires ARGOCD_URL for actual API calls, but router is always available)
app.include_router(argocd_router.router)

# Pipeline orchestration (always registered — repo_path can be dynamic)
app.include_router(pipeline_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/diagnostics")
def diagnostics():
    """Safe runtime snapshot for debugging (no secrets). Use after reproduce: curl http://localhost:8000/diagnostics"""
    from .env_loader import load_all_env
    load_all_env()
    agents = agent_loader.list_agents()
    url_set = bool(os.getenv("CURSOR_API_URL", "").strip())
    key_set = bool(os.getenv("CURSOR_API_KEY", "").strip())
    http_only = os.getenv("CODE_AGENTS_HTTP_ONLY", "").strip().lower() in ("1", "true", "yes")
    has_cursor = any(getattr(a, "backend", "") == "cursor" for a in agents)
    try:
        package_version = importlib.metadata.version("code-agents")
    except importlib.metadata.PackageNotFoundError:
        package_version = "dev"
    return {
        "cursor_api_url_set": url_set,
        "cursor_api_key_set": key_set,
        "code_agents_http_only": http_only,
        "cursor_agents_use_cli_without_http": has_cursor and not url_set,
        "cursor_would_fail_fast_http_only": http_only and has_cursor and not url_set,
        "open_webui_hint": (
            "Per-agent API base URLs (…/v1/agents/<name>) expose only that agent. "
            "To use agent-router, either set base URL to http://HOST:PORT/v1 and pick model agent-router, "
            "or add a connection with base URL …/v1/agents/agent-router."
        ),
        "code_agents_public_base_url": code_agents_public_base_url(),
        "openai_api_base_url": f"{code_agents_public_base_url()}/v1",
        "atlassian_cloud_site_url": atlassian_cloud_site_url(),
        "atlassian_oauth_sign_in": (
            f"{code_agents_public_base_url()}/oauth/atlassian/"
            if os.getenv("ATLASSIAN_OAUTH_CLIENT_ID", "").strip()
            else None
        ),
        "elasticsearch_configured": bool(
            os.getenv("ELASTICSEARCH_URL", "").strip() or os.getenv("ELASTICSEARCH_CLOUD_ID", "").strip()
        ),
        "elasticsearch_info_path": "/elasticsearch/info",
        "target_repo_configured": bool(os.getenv("TARGET_REPO_PATH", "").strip()),
        "jenkins_configured": bool(os.getenv("JENKINS_URL", "").strip()),
        "argocd_configured": bool(os.getenv("ARGOCD_URL", "").strip()),
        "pipeline_enabled": any(
            os.getenv(v, "").strip() for v in ("JENKINS_URL", "ARGOCD_URL", "TARGET_REPO_PATH")
        ),
        "agents": [{"name": a.name, "backend": getattr(a, "backend", "")} for a in agents],
        "process_cwd": os.getcwd(),
        "backend_py": os.path.abspath(getattr(_backend_mod, "__file__", "") or ""),
        "package_version": package_version,
    }
