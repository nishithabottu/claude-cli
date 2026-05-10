"""Offline tests for claude_cli.

We mock the Anthropic SDK so these run with no API key and no network.
"""

from __future__ import annotations

import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from claude_cli import __main__ as cli


# A representative valid response Claude might return for the README example.
VALID_RESPONSE = json.dumps(
    {
        "severity": "error",
        "service": "auth-api",
        "summary": "Token issuance failed because the JWT signature was expired.",
        "likely_cause": "Clock skew or stale signing key in token_service.py.",
        "evidence": ["jwt.ExpiredSignatureError", "token_service.py"],
        "error_code": None,
    }
)


def _fake_client(response_text: str):
    """Build a fake Anthropic client whose .messages.create returns response_text."""
    fake_message = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=response_text)]
    )
    fake_messages = SimpleNamespace(create=lambda **kwargs: fake_message)
    return SimpleNamespace(messages=fake_messages)


def test_load_schema_returns_pydantic_class():
    cls = cli.load_schema("schemas.RootCause")
    from schemas import RootCause

    assert cls is RootCause


def test_load_schema_rejects_non_pydantic():
    with pytest.raises(TypeError):
        # ``str`` is a class but not a BaseModel subclass.
        cli.load_schema("builtins.str")


def test_build_system_prompt_includes_json_schema():
    from schemas import RootCause

    prompt = cli.build_system_prompt("be terse", RootCause)
    assert "be terse" in prompt
    # The injected schema should mention our field names.
    assert "severity" in prompt and "service" in prompt
    assert "JSON Schema" in prompt


def test_validate_and_dump_round_trips_valid_response():
    from schemas import RootCause

    out = cli.validate_and_dump(VALID_RESPONSE, RootCause)
    parsed = json.loads(out)
    assert parsed["service"] == "auth-api"
    assert parsed["severity"] == "error"


def test_validate_and_dump_strips_markdown_fences():
    from schemas import RootCause

    fenced = f"```json\n{VALID_RESPONSE}\n```"
    out = cli.validate_and_dump(fenced, RootCause)
    assert json.loads(out)["service"] == "auth-api"


def test_validate_and_dump_rejects_bad_payload():
    from schemas import RootCause
    from pydantic import ValidationError

    bad = json.dumps({"severity": "error"})  # missing required fields
    with pytest.raises(ValidationError):
        cli.validate_and_dump(bad, RootCause)


def test_main_with_schema_writes_validated_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("any log line here\n"))
    # stdin.isatty() is read on the io.StringIO above; StringIO returns False.
    monkeypatch.setattr(cli, "Anthropic", lambda: _fake_client(VALID_RESPONSE))

    rc = cli.main(["--schema", "schemas.RootCause"])
    assert rc == 0

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["service"] == "auth-api"


def test_main_without_schema_writes_raw_text(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello\n"))
    monkeypatch.setattr(cli, "Anthropic", lambda: _fake_client("hi back!"))

    rc = cli.main([])
    assert rc == 0
    assert "hi back!" in capsys.readouterr().out
