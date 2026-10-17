"""Verify real GitHub + AI evaluation against a running configured backend."""

from smoke_evaluation import main

if __name__ == "__main__":
    raise SystemExit(main(default_source="github"))
