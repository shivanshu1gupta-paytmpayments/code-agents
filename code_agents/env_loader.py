"""
Centralized .env loading for Code Agents.

Two-tier config:
  1. Global:   ~/.code-agents/config.env  (API keys, server, integrations)
  2. Per-repo: {repo}/.env.code-agents    (Jenkins, ArgoCD, testing overrides)

Legacy {cwd}/.env files are still loaded for backward compatibility.
TARGET_REPO_PATH is always derived from cwd — never stored in config files.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

GLOBAL_ENV_PATH = Path.home() / ".code-agents" / "config.env"
PER_REPO_FILENAME = ".env.code-agents"

# ---------------------------------------------------------------------------
# Variable classification
# ---------------------------------------------------------------------------

# Variables that belong in the global config (shared across all repos)
GLOBAL_VARS = {
    # Core
    "CURSOR_API_KEY", "ANTHROPIC_API_KEY", "CURSOR_API_URL", "CODE_AGENTS_HTTP_ONLY",
    "CODE_AGENTS_BACKEND", "CODE_AGENTS_CLAUDE_CLI_MODEL",
    # Server
    "HOST", "PORT", "LOG_LEVEL", "AGENTS_DIR",
    "CODE_AGENTS_PUBLIC_BASE_URL", "OPEN_WEBUI_PUBLIC_URL",
    # Atlassian
    "ATLASSIAN_OAUTH_CLIENT_ID", "ATLASSIAN_OAUTH_CLIENT_SECRET",
    "ATLASSIAN_OAUTH_SCOPES", "ATLASSIAN_OAUTH_SUCCESS_REDIRECT",
    "ATLASSIAN_CLOUD_SITE_URL", "CODE_AGENTS_HTTPS_VERIFY",
    # Elasticsearch
    "ELASTICSEARCH_URL", "ELASTICSEARCH_CLOUD_ID", "ELASTICSEARCH_API_KEY",
    "ELASTICSEARCH_USERNAME", "ELASTICSEARCH_PASSWORD",
    "ELASTICSEARCH_CA_CERTS", "ELASTICSEARCH_VERIFY_SSL",
    # Redash
    "REDASH_BASE_URL", "REDASH_API_KEY", "REDASH_USERNAME", "REDASH_PASSWORD",
}

# Variables that belong in the per-repo config
REPO_VARS = {
    # Jenkins
    "JENKINS_URL", "JENKINS_USERNAME", "JENKINS_API_TOKEN",
    "JENKINS_BUILD_JOB", "JENKINS_DEPLOY_JOB",
    # ArgoCD
    "ARGOCD_URL", "ARGOCD_AUTH_TOKEN", "ARGOCD_APP_NAME", "ARGOCD_VERIFY_SSL",
    # Testing
    "TARGET_TEST_COMMAND", "TARGET_COVERAGE_THRESHOLD", "TARGET_REPO_REMOTE",
}

# Never stored — always computed at runtime
RUNTIME_VARS = {"TARGET_REPO_PATH"}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_all_env(cwd: str | None = None) -> None:
    """
    Load environment from global config, legacy .env, and per-repo overrides.

    Load order (later sources override earlier ones):
      1. ~/.code-agents/config.env  (global defaults, override=False — only sets unset vars)
      2. {cwd}/.env                 (legacy fallback, override=True — overrides global)
      3. {cwd}/.env.code-agents     (per-repo overrides, override=True — overrides both)
      4. TARGET_REPO_PATH            (always set from cwd at runtime, never stored)

    Precedence: per-repo > legacy .env > global config > existing env vars
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        # dotenv not available — env vars must be set manually
        cwd = cwd or os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()
        os.environ.setdefault("TARGET_REPO_PATH", cwd)
        return

    cwd = cwd or os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()

    # 1. Global config
    if GLOBAL_ENV_PATH.is_file():
        load_dotenv(GLOBAL_ENV_PATH, override=False)

    # 2. Legacy per-repo .env (backward compatibility)
    legacy = Path(cwd) / ".env"
    if legacy.is_file():
        load_dotenv(legacy, override=True)

    # 3. Per-repo overrides
    repo_env = Path(cwd) / PER_REPO_FILENAME
    if repo_env.is_file():
        load_dotenv(repo_env, override=True)

    # 4. TARGET_REPO_PATH is always runtime
    os.environ.setdefault("TARGET_REPO_PATH", cwd)


def split_vars(env_vars: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Split a dict of env vars into (global_vars, repo_vars)."""
    g, r = {}, {}
    for k, v in env_vars.items():
        if k in RUNTIME_VARS:
            continue  # never store
        elif k in REPO_VARS:
            r[k] = v
        else:
            g[k] = v  # default to global
    return g, r
