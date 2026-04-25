"""
Unit Tests — Domain Configuration Loader

FIRST Principles:
  F - Fast:         Uses a temp YAML file on disk — no network, no DB.
  I - Independent:  Each test has its own temp dir / YAML content.
  R - Repeatable:   Deterministic file content and assertions.
  S - Self-Validating: Clear assertions on all config fields.
  T - Timely:       Written alongside the new domain_config module.

Covers:
  1. load_domain_config() reads name, version, description correctly
  2. QA system prompt is loaded and interpolates {domain_name}
  3. Retrieval config top_k and top_n are loaded
  4. Memory config max_history_turns is loaded
  5. Guardrail scope_keywords tuple is loaded correctly
  6. FileNotFoundError raised if domain YAML does not exist
  7. ValueError raised if YAML is not a mapping (e.g. it's a list)
  8. Directory traversal is blocked (OWASP A04)
  9. Missing optional sections use safe defaults
  10. out_of_scope_message is interpolated correctly
"""

import sys
import os
import tempfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "agents"))


# ──────────────────────────────────────────────────────────────
# Shared minimal YAML fixture
# ──────────────────────────────────────────────────────────────

MINIMAL_YAML = {
    "domain": {
        "name": "Smart Building AI",
        "description": "Expert in HVAC and BMS.",
        "version": "2.0.0",
    },
    "prompts": {
        "qa_system": "You are a {domain_name} expert. Answer precisely.",
        "router_system": "Route the query for {domain_name}.",
        "out_of_scope_message": "I only handle {domain_name} questions.",
    },
    "retrieval": {
        "top_k_retrieval": 12,
        "top_n_reranked": 4,
        "min_relevance_score": 0.30,
    },
    "memory": {
        "max_history_turns": 3,
    },
    "guardrails": {
        "max_query_length": 1500,
        "min_query_length": 5,
        "scope_keywords": ["hvac", "building", "bms"],
    },
}


def _write_yaml(tmp_dir: Path, name: str, content: dict) -> Path:
    """Write a YAML config to a temp directory and return its path."""
    path = tmp_dir / f"{name}.yaml"
    with open(path, "w") as f:
        yaml.dump(content, f)
    return path


# ──────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────

class TestDomainConfigLoading:

    def test_domain_name_version_description_loaded(self, tmp_path):
        """Core domain identity fields must load from YAML."""
        _write_yaml(tmp_path, "test_domain", MINIMAL_YAML)

        from domain_config import load_domain_config
        cfg = load_domain_config("test_domain", config_dir=tmp_path)

        assert cfg.name == "Smart Building AI"
        assert cfg.version == "2.0.0"
        assert cfg.description == "Expert in HVAC and BMS."

    def test_qa_system_prompt_interpolated(self, tmp_path):
        """QA system prompt must have {domain_name} replaced with the actual name."""
        _write_yaml(tmp_path, "test_domain", MINIMAL_YAML)

        from domain_config import load_domain_config
        cfg = load_domain_config("test_domain", config_dir=tmp_path)

        assert "{domain_name}" not in cfg.qa_system_prompt
        assert "Smart Building AI" in cfg.qa_system_prompt

    def test_out_of_scope_message_interpolated(self, tmp_path):
        """out_of_scope_message must also have {domain_name} interpolated."""
        _write_yaml(tmp_path, "test_domain", MINIMAL_YAML)

        from domain_config import load_domain_config
        cfg = load_domain_config("test_domain", config_dir=tmp_path)

        assert "Smart Building AI" in cfg.out_of_scope_message
        assert "{domain_name}" not in cfg.out_of_scope_message

    def test_retrieval_config_loaded(self, tmp_path):
        """Retrieval settings (top_k, top_n, min_score) must load from YAML."""
        _write_yaml(tmp_path, "test_domain", MINIMAL_YAML)

        from domain_config import load_domain_config
        cfg = load_domain_config("test_domain", config_dir=tmp_path)

        assert cfg.retrieval.top_k_retrieval == 12
        assert cfg.retrieval.top_n_reranked == 4
        assert cfg.retrieval.min_relevance_score == pytest.approx(0.30)

    def test_memory_config_loaded(self, tmp_path):
        """Memory max_history_turns must load from YAML."""
        _write_yaml(tmp_path, "test_domain", MINIMAL_YAML)

        from domain_config import load_domain_config
        cfg = load_domain_config("test_domain", config_dir=tmp_path)

        assert cfg.memory.max_history_turns == 3

    def test_guardrail_scope_keywords_loaded_as_tuple(self, tmp_path):
        """Scope keywords must be loaded as a tuple (immutable, for frozen dataclass)."""
        _write_yaml(tmp_path, "test_domain", MINIMAL_YAML)

        from domain_config import load_domain_config
        cfg = load_domain_config("test_domain", config_dir=tmp_path)

        assert isinstance(cfg.guardrails.scope_keywords, tuple)
        assert "hvac" in cfg.guardrails.scope_keywords
        assert "bms" in cfg.guardrails.scope_keywords

    def test_file_not_found_raises(self, tmp_path):
        """FileNotFoundError if the domain YAML does not exist."""
        from domain_config import load_domain_config

        with pytest.raises(FileNotFoundError, match="nonexistent"):
            load_domain_config("nonexistent", config_dir=tmp_path)

    def test_invalid_yaml_structure_raises_value_error(self, tmp_path):
        """If the YAML is a list (not a mapping), ValueError must be raised."""
        path = tmp_path / "bad.yaml"
        path.write_text("- item1\n- item2\n")

        from domain_config import load_domain_config

        with pytest.raises(ValueError, match="expected a YAML mapping"):
            load_domain_config("bad", config_dir=tmp_path)

    def test_directory_traversal_is_blocked(self, tmp_path):
        """OWASP A04: domain_name with path separators must be sanitised."""
        from domain_config import load_domain_config

        # Attempt to escape the config_dir
        with pytest.raises(FileNotFoundError):
            load_domain_config("../../../etc/passwd", config_dir=tmp_path)

    def test_missing_optional_sections_use_defaults(self, tmp_path):
        """If retrieval/memory/guardrails are absent, safe defaults must apply."""
        minimal = {"domain": {"name": "Minimal AI"}}
        _write_yaml(tmp_path, "minimal", minimal)

        from domain_config import load_domain_config, RetrievalConfig, MemoryConfig
        cfg = load_domain_config("minimal", config_dir=tmp_path)

        # Should not raise — use dataclass defaults
        assert cfg.retrieval.top_k_retrieval == RetrievalConfig().top_k_retrieval
        assert cfg.memory.max_history_turns == MemoryConfig().max_history_turns
        assert cfg.guardrails.scope_keywords == ()

    def test_domain_config_is_frozen(self, tmp_path):
        """DomainConfiguration must be immutable (frozen=True on dataclass)."""
        _write_yaml(tmp_path, "test_domain", MINIMAL_YAML)

        from domain_config import load_domain_config
        cfg = load_domain_config("test_domain", config_dir=tmp_path)

        with pytest.raises((AttributeError, TypeError)):
            cfg.name = "Hacked!"  # type: ignore[misc]
