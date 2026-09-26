"""Fetch one immutable Thames Water discharge-status evidence bundle."""

from watergeo.ingestion.thames_discharge_client import fetch_snapshot

if __name__ == "__main__":
    print(fetch_snapshot())
