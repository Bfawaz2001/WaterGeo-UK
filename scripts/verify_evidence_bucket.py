"""Configure or verify the production evidence bucket without logging secrets."""

from watergeo.operations.evidence_bucket import main

if __name__ == "__main__":
    raise SystemExit(main())
