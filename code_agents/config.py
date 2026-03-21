from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_SYSTEM_PROMPT_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_system_prompt_env(s: str) -> str:
    """Replace ${VAR} in YAML system_prompt with env or sensible defaults (after load_dotenv)."""

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key == "CODE_AGENTS_PUBLIC_BASE_URL":
            v = os.getenv(key, "").strip()
            return v if v else f"http://127.0.0.1:{settings.port}"
        if key == "ATLASSIAN_CLOUD_SITE_URL":
            v = os.getenv(key, "").strip()
            return v if v else "(set ATLASSIAN_CLOUD_SITE_URL in .env)"
        val = os.getenv(key)
        return val if val is not None and val != "" else m.group(0)

    return _SYSTEM_PROMPT_ENV.sub(repl, s)


@dataclass
class AgentConfig:
    name: str
    display_name: str
    backend: str  # "cursor" or "claude"
    model: str
    system_prompt: str = ""
    permission_mode: str = "default"
    cwd: str = "."
    api_key: Optional[str] = None  # CURSOR_API_KEY or ANTHROPIC_API_KEY; env var fallback
    stream_tool_activity: bool = True
    include_session: bool = True
    extra_args: dict = field(default_factory=dict)


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 8000
    agents_dir: str = str(Path(__file__).resolve().parent.parent / "agents")


settings = Settings(
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "8000")),
    agents_dir=os.getenv("AGENTS_DIR", str(Path(__file__).resolve().parent.parent / "agents")),
)


class AgentLoader:
    """Reads YAML files from the agents directory and builds a name → config registry."""

    def __init__(self, agents_dir: str | Path):
        self._dir = Path(agents_dir)
        self._agents: dict[str, AgentConfig] = {}

    def _load_file(self, path: Path) -> None:
        with open(path) as f:
            data = yaml.safe_load(f)
        if not data or "name" not in data:
            return
        api_key = data.get("api_key")
        if api_key and isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
            api_key = os.getenv(api_key[2:-1], None)

        extra_args = data.get("extra_args") or {}
        if isinstance(extra_args, dict):
            expanded = {}
            for k, v in extra_args.items():
                if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                    expanded[k] = os.getenv(v[2:-1], v)
                else:
                    expanded[k] = v
            extra_args = expanded

        raw_prompt = data.get("system_prompt", "")
        if isinstance(raw_prompt, str) and raw_prompt:
            raw_prompt = _expand_system_prompt_env(raw_prompt)

        cfg = AgentConfig(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            backend=data.get("backend", "cursor"),
            model=data.get("model", "composer 1.5"),
            system_prompt=raw_prompt if isinstance(raw_prompt, str) else "",
            permission_mode=data.get("permission_mode", "default"),
            cwd=data.get("cwd", "."),
            api_key=api_key,
            stream_tool_activity=data.get("stream_tool_activity", True),
            include_session=data.get("include_session", True),
            extra_args=extra_args,
        )
        self._agents[cfg.name] = cfg

    def load(self) -> None:
        self._agents.clear()
        if not self._dir.is_dir():
            raise FileNotFoundError(f"Agents directory not found: {self._dir}")
        for path in sorted(self._dir.glob("*.yaml")):
            self._load_file(path)
        for path in sorted(self._dir.glob("*.yml")):
            self._load_file(path)

    def get(self, name: str) -> Optional[AgentConfig]:
        return self._agents.get(name)

    def list_agents(self) -> list[AgentConfig]:
        return list(self._agents.values())

    @property
    def default(self) -> Optional[AgentConfig]:
        agents = self.list_agents()
        return agents[0] if agents else None


agent_loader = AgentLoader(settings.agents_dir)
