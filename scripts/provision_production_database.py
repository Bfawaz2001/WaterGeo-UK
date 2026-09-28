"""Provision managed production database roles without persisting credentials."""

from watergeo.operations.production_database import main

if __name__ == "__main__":
    raise SystemExit(main(["provision"]))
