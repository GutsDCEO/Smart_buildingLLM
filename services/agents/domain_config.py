"""
Domain Configuration Loader — Reads externalized AI personality from YAML.

Design:
  - SRP: Only loads and validates domain configuration. No business logic.
  - OCP: Adding new config sections requires only updating the dataclass + YAML.
  - OWASP A04: Validates file paths to prevent directory traversal.
  - OWASP A02: No secrets in YAML — secrets stay in .env only.

Usage:
  from domain_config import domain_config
  prompt = domain_config.qa_system_prompt  # Already interpolated
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Default paths — Docker mount at /config/domains, fallback to project-relative
_DOCKER_CONFIG_DIR = Path("/config/domains")
_PROJECT_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "domains"
_DEFAULT_CONFIG_DIR = _DOCKER_CONFIG_DIR if _DOCKER_CONFIG_DIR.exists() else _PROJECT_CONFIG_DIR
_DEFAULT_DOMAIN = "smart_building"


@dataclass(frozen=True)
class RetrievalConfig:
    """Retrieval pipeline settings."""
    top_k_retrieval: int = 15
    top_n_reranked: int = 5
    min_relevance_score: float = 0.25


@dataclass(frozen=True)
class MemoryConfig:
    """Conversation memory settings."""
    max_history_turns: int = 5


@dataclass(frozen=True)
class GuardrailConfig:
    """Input validation settings."""
    max_query_length: int = 2000
    min_query_length: int = 3
    scope_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainConfiguration:
    """
    Immutable, fully-loaded domain configuration.

    All prompt templates have placeholders already resolved.
    """
    # Domain identity
    name: str = "Smart Building AI"
    description: str = ""
    version: str = "1.0.0"

    # Prompts (pre-interpolated)
    qa_system_prompt: str = ""
    router_system_prompt: str = ""
    out_of_scope_message: str = ""

    # Sub-configurations
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    guardrails: GuardrailConfig = field(default_factory=GuardrailConfig)


def load_domain_config(
    domain_name: Optional[str] = None,
    config_dir: Optional[Path] = None,
) -> DomainConfiguration:
    """
    Load and validate a domain configuration from YAML.

    Args:
        domain_name: Name of the domain (maps to {name}.yaml).
                     Defaults to DOMAIN_CONFIG env var or 'smart_building'.
        config_dir:  Directory containing domain YAML files.
                     Defaults to project_root/config/domains/.

    Returns:
        A frozen DomainConfiguration instance.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValueError: If the YAML is malformed or missing required fields.
    """
    import os
    domain_name = domain_name or os.getenv("DOMAIN_CONFIG", _DEFAULT_DOMAIN)
    config_dir = config_dir or _DEFAULT_CONFIG_DIR

    # OWASP A04: Prevent directory traversal
    safe_name = Path(domain_name).name  # Strip any path components
    config_path = config_dir / f"{safe_name}.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Domain config not found: {config_path}. "
            f"Create it or set DOMAIN_CONFIG env var."
        )

    logger.info("Loading domain config from '%s'.", config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Invalid domain config: expected a YAML mapping, got {type(raw)}")

    # Extract sections with safe defaults
    domain_section = raw.get("domain", {})
    prompts_section = raw.get("prompts", {})
    guardrails_section = raw.get("guardrails", {})
    retrieval_section = raw.get("retrieval", {})
    memory_section = raw.get("memory", {})

    domain_name_str = domain_section.get("name", "AI Assistant")

    # Interpolate {domain_name} placeholders in prompts
    qa_prompt = prompts_section.get("qa_system", "").replace(
        "{domain_name}", domain_name_str
    )
    router_prompt = prompts_section.get("router_system", "").replace(
        "{domain_name}", domain_name_str
    )
    oos_message = prompts_section.get("out_of_scope_message", "").replace(
        "{domain_name}", domain_name_str
    )

    config = DomainConfiguration(
        name=domain_name_str,
        description=domain_section.get("description", ""),
        version=domain_section.get("version", "1.0.0"),
        qa_system_prompt=qa_prompt.strip(),
        router_system_prompt=router_prompt.strip(),
        out_of_scope_message=oos_message.strip(),
        retrieval=RetrievalConfig(
            top_k_retrieval=retrieval_section.get("top_k_retrieval", 15),
            top_n_reranked=retrieval_section.get("top_n_reranked", 5),
            min_relevance_score=retrieval_section.get("min_relevance_score", 0.25),
        ),
        memory=MemoryConfig(
            max_history_turns=memory_section.get("max_history_turns", 5),
        ),
        guardrails=GuardrailConfig(
            max_query_length=guardrails_section.get("max_query_length", 2000),
            min_query_length=guardrails_section.get("min_query_length", 3),
            scope_keywords=tuple(guardrails_section.get("scope_keywords", [])),
        ),
    )

    logger.info(
        "Domain config loaded: '%s' v%s (%d scope keywords, top_k=%d, top_n=%d).",
        config.name,
        config.version,
        len(config.guardrails.scope_keywords),
        config.retrieval.top_k_retrieval,
        config.retrieval.top_n_reranked,
    )

    return config


# ── Singleton ────────────────────────────────────────────────
# Loaded once at import time. Thread-safe because frozen.
# To reload: restart the service or call load_domain_config() explicitly.
try:
    domain_config = load_domain_config()
except FileNotFoundError:
    logger.warning(
        "Domain config YAML not found. Using built-in defaults. "
        "This is fine for development but not for production."
    )
    domain_config = DomainConfiguration()
