#!/usr/bin/env python3
"""Quick check that the Anthropic API key in .env actually works.

Reuses the app's Settings so it reads the same ANTHROPIC_API_KEY / AGENT_MODEL
the agent uses, then makes one tiny live API call.

Usage:
    python -m scripts.check_anthropic_key
    # or
    python scripts/check_anthropic_key.py

Exit code 0 = key works, 1 = it doesn't (with a reason printed).
"""
from __future__ import annotations

import sys


def main() -> int:
    try:
        from anthropic import (
            Anthropic,
            APIConnectionError,
            APIStatusError,
            AuthenticationError,
        )
    except ImportError:
        print("FAIL: `anthropic` not installed. Run: pip install -r app/requirements.txt")
        return 1

    # Pull the key + model from the app's own config (reads .env).
    try:
        from app.config import get_settings  # type: ignore

        settings = get_settings()
        api_key = settings.anthropic_api_key
        model = settings.agent_model
    except Exception:
        # Fall back to the raw env var if the app package isn't importable.
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        model = os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")

    if not api_key:
        print("FAIL: ANTHROPIC_API_KEY is empty. Set it in .env.")
        return 1

    masked = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "(too short)"
    print(f"Using key {masked} with model {model} ...")

    client = Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=8,
            messages=[{"role": "user", "content": "Reply with the single word: pong"}],
        )
    except AuthenticationError as e:
        print(f"FAIL: authentication rejected (bad/expired key). {e}")
        return 1
    except APIStatusError as e:
        # e.g. 403 (no model access), 429 (rate/credit), 400 (bad model name).
        print(f"FAIL: API returned status {e.status_code}. {e.message}")
        return 1
    except APIConnectionError as e:
        print(f"FAIL: could not reach the Anthropic API. {e}")
        return 1

    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    print(f"OK: key works. Model replied: {text!r}")
    print(f"    tokens — in: {resp.usage.input_tokens}, out: {resp.usage.output_tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
