"""Verify real sample evaluation, health, CORS and invalid-request handling."""

from smoke_evaluation import main

if __name__ == "__main__":
    raise SystemExit(main(default_source="sample"))
