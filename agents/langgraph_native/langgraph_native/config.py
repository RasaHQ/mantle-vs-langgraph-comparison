"""Agent settings from ``data/agent.yml`` and the environment."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

DEFAULT_MODEL = "gpt-5.2"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_MCP_SERVER_URL = "http://localhost:8001/mcp/"
DEFAULT_MCP_TOKEN = "test-token"
MCP_SERVER_NAME = "mock_tools"

VOICE_CHANNEL = "voice"


class FillerExample(BaseModel):
    """One example of a short sentence spoken before a tool call."""

    model_config = ConfigDict(frozen=True)

    user: str
    filler: str


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class AgentConfig(BaseModel):
    """Persona, rules, channel rules, fillers, models, and the MCP server."""

    model_config = ConfigDict(frozen=True)

    persona: str
    rules: list[str]
    text_rules: str = ""
    voice_rules: str = ""
    fillers_enabled: bool = False
    filler_examples: list[FillerExample] = Field(default_factory=list)
    model: str = DEFAULT_MODEL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    mcp_server_url: str = DEFAULT_MCP_SERVER_URL
    mcp_token: str = DEFAULT_MCP_TOKEN
    router_first: bool = False
    skill_catalog_each_turn: bool = False

    def channel_rules(self, channel: str) -> str:
        """Returns the voice rules on the voice channel, else the text rules."""
        return self.voice_rules if channel == VOICE_CHANNEL else self.text_rules

    def fillers_on(self, channel: str) -> bool:
        """Test if the agent speaks a filler before tool calls on *channel*."""
        return self.fillers_enabled and channel == VOICE_CHANNEL


def load_config(data_dir: Path = DATA_DIR) -> AgentConfig:
    """Returns the settings in ``<data_dir>/agent.yml`` with environment overrides."""
    document = yaml.safe_load((data_dir / "agent.yml").read_text(encoding="utf-8"))
    channel_rules = document.get("channel_rules") or {}
    fillers = document.get("fillers") or {}
    routing = document.get("routing") or {}
    router_first = _env_flag(
        "LANGGRAPH_ROUTER_FIRST", bool(routing.get("router_first"))
    )
    skill_catalog = _env_flag(
        "LANGGRAPH_SKILL_CATALOG",
        bool(routing.get("skill_catalog_each_turn")),
    )
    return AgentConfig(
        persona=str(document["persona"]).strip(),
        rules=[str(rule).strip() for rule in document.get("rules") or []],
        text_rules=str(channel_rules.get("text") or "").strip(),
        voice_rules=str(channel_rules.get("voice") or "").strip(),
        fillers_enabled=bool(fillers.get("enabled")),
        filler_examples=fillers.get("examples") or [],
        model=os.environ.get("LANGGRAPH_AGENT_MODEL", DEFAULT_MODEL),
        mcp_server_url=os.environ.get("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL),
        mcp_token=os.environ.get("MCP_BANKING_TOKEN") or DEFAULT_MCP_TOKEN,
        router_first=router_first,
        skill_catalog_each_turn=skill_catalog,
    )
