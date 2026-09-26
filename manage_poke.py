"""Backward-compatible entry point for the former Poke-specific manager."""

from manage_mcp import main


if __name__ == "__main__":
    raise SystemExit(main())
