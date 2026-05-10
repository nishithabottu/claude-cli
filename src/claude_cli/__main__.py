"""claude-cli entry point.

Pipes stdin into Claude. With --schema, the response is validated against a
Pydantic model and printed as JSON. Without --schema, the response is printed
as plain text.

Usage:
    cat error.log | claude-cli --schema schemas.RootCause
    echo "summarize this" | claude-cli --system "be terse" --stream
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from typing import Optional, Type

from anthropic import Anthropic
from pydantic import BaseModel, ValidationError


DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 1024


def load_schema(dotted_path: str) -> Type[BaseModel]:
    """Load a Pydantic BaseModel subclass from a dotted import path.

    Example: ``schemas.RootCause`` -> imports ``schemas`` and returns
    ``schemas.RootCause``.
    """
    if "." not in dotted_path:
        raise ValueError(
            f"--schema must be a dotted path like 'module.ClassName', got {dotted_path!r}"
        )
    module_name, class_name = dotted_path.rsplit(".", 1)

    # Make sure the user's CWD is on sys.path so local schema modules import.
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise AttributeError(f"{module_name!r} has no attribute {class_name!r}")
    if not (isinstance(cls, type) and issubclass(cls, BaseModel)):
        raise TypeError(f"{dotted_path} is not a pydantic.BaseModel subclass")
    return cls


def build_system_prompt(
    user_system: Optional[str], schema: Optional[Type[BaseModel]]
) -> str:
    """Compose the final system prompt, appending JSON-schema discipline if needed."""
    parts: list[str] = []
    if user_system:
        parts.append(user_system.strip())
    if schema is not None:
        json_schema = json.dumps(schema.model_json_schema(), indent=2)
        parts.append(
            "You MUST respond with a single JSON object that conforms exactly to "
            "the following JSON Schema. Do not include prose, markdown fences, or "
            "any text outside the JSON object.\n\n"
            f"JSON Schema:\n{json_schema}"
        )
    return "\n\n".join(parts) if parts else "You are a helpful assistant."


def call_claude(
    client: Anthropic,
    *,
    model: str,
    system: str,
    user_input: str,
    max_tokens: int,
    stream: bool,
) -> str:
    """Send the request to Claude. Returns the full text response.

    When ``stream=True`` we tee the streamed tokens to stderr so the user sees
    progress, but still return the assembled string for schema validation.
    """
    if stream:
        chunks: list[str] = []
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_input}],
        ) as s:
            for text in s.text_stream:
                chunks.append(text)
                sys.stderr.write(text)
                sys.stderr.flush()
        sys.stderr.write("\n")
        return "".join(chunks)

    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_input}],
    )
    # Claude returns a list of content blocks; concatenate the text ones.
    return "".join(block.text for block in msg.content if getattr(block, "type", None) == "text")


def validate_and_dump(raw: str, schema: Type[BaseModel]) -> str:
    """Parse ``raw`` as JSON via the schema, raise ValidationError on failure,
    return a canonicalized JSON string."""
    # Be a little forgiving: strip ``` fences if Claude added them anyway.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        # drop optional language tag on first line
        if "\n" in cleaned:
            first, rest = cleaned.split("\n", 1)
            if first.strip().lower() in {"json", ""}:
                cleaned = rest
    obj = schema.model_validate_json(cleaned)
    return obj.model_dump_json(indent=2)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="claude-cli",
        description="Pipe stdin into Claude. Optionally validate against a Pydantic schema.",
    )
    p.add_argument("--system", help="System prompt prepended to the request.")
    p.add_argument(
        "--schema",
        help="Dotted path to a Pydantic BaseModel subclass (e.g. schemas.RootCause). "
        "When set, the response is validated and re-serialized as JSON.",
    )
    p.add_argument(
        "--stream",
        action="store_true",
        help="Stream tokens to stderr as they arrive (final output still goes to stdout).",
    )
    p.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Anthropic model name (default: {DEFAULT_MODEL}).",
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Max tokens in the response (default: {DEFAULT_MAX_TOKENS}).",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if sys.stdin.isatty():
        sys.stderr.write(
            "claude-cli: no stdin detected. Pipe text in, e.g.:\n"
            "  echo 'hello' | claude-cli\n"
        )
        return 2

    user_input = sys.stdin.read()
    if not user_input.strip():
        sys.stderr.write("claude-cli: stdin was empty.\n")
        return 2

    schema: Optional[Type[BaseModel]] = None
    if args.schema:
        try:
            schema = load_schema(args.schema)
        except (ImportError, AttributeError, TypeError, ValueError) as e:
            sys.stderr.write(f"claude-cli: failed to load schema {args.schema!r}: {e}\n")
            return 2

    system_prompt = build_system_prompt(args.system, schema)
    client = Anthropic()  # picks up ANTHROPIC_API_KEY from env

    try:
        raw = call_claude(
            client,
            model=args.model,
            system=system_prompt,
            user_input=user_input,
            max_tokens=args.max_tokens,
            stream=args.stream,
        )
    except Exception as e:  # surface API errors cleanly without a traceback
        sys.stderr.write(f"claude-cli: API call failed: {e}\n")
        return 1

    if schema is None:
        sys.stdout.write(raw)
        if not raw.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    try:
        dumped = validate_and_dump(raw, schema)
    except (ValidationError, json.JSONDecodeError) as e:
        sys.stderr.write(
            "claude-cli: response did not match schema.\n"
            f"  error: {e}\n"
            f"  raw response:\n{raw}\n"
        )
        return 1

    sys.stdout.write(dumped + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
