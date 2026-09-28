"""Run non-mutating production deployment preflight checks."""

from watergeo.operations.production_preflight import main

if __name__ == "__main__":
    raise SystemExit(main())
