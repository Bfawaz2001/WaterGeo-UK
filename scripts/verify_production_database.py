"""Verify managed production database identities and grants."""

from watergeo.operations.production_database import main

if __name__ == "__main__":
    raise SystemExit(main(["verify"]))
