# claude-cli

A pip-installable Python CLI that pipes stdin into Claude with structured outputs.

```bash
cat samples/error.log | claude-cli --schema schemas.RootCause
```

…and you get back validated JSON, not a paragraph you have to parse.

## Why

Built to scratch a real itch — I kept reaching for Claude in shell scripts and
writing the same boilerplate every time. Production LLM tools live or die on
output discipline, so this one bakes Pydantic validation in at the boundary.

## Install

```bash
git clone https://github.com/<you>/claude-cli && cd claude-cli
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
```

## Worked example

`schemas.py` defines a `RootCause` Pydantic model. Pipe a log line through
the CLI with `--schema`, and the response is a JSON object that matches the
schema exactly:

```bash
echo '2026-05-09T14:32:11Z [ERROR] auth-api: jwt.ExpiredSignatureError at token_service.py:142' \
  | claude-cli --schema schemas.RootCause
```

```json
{
  "severity": "error",
  "service": "auth-api",
  "summary": "JWT signature was expired during token issuance.",
  "likely_cause": "Stale signing key or clock skew in token_service.py.",
  "evidence": ["jwt.ExpiredSignatureError", "token_service.py"],
  "error_code": null
}
```

## Flags

| flag            | what it does                                              |
| --------------- | --------------------------------------------------------- |
| `--system`      | system prompt prepended to the request                    |
| `--schema`      | dotted path to a Pydantic model (e.g. `schemas.RootCause`)|
| `--stream`      | stream tokens to stderr while assembling the response     |
| `--model`       | Anthropic model name (default: `claude-sonnet-4-6`)       |
| `--max-tokens`  | response token cap (default: 1024)                        |

## Eval

The success metric: `samples/error.log` has 10 hand-authored log lines.
`scripts/eval.sh` pipes each through the CLI with `--schema schemas.RootCause`
and counts how many produce valid Pydantic-typed JSON. Target: ≥ 9 / 10.

```bash
./scripts/eval.sh
# Result: 10/10 valid responses (run on 2026-05-10, claude-sonnet-4-6)
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT.
