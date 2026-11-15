"""Read-only company response scan; never changes verification policy or runtime."""

import argparse
import json
from pathlib import Path

import httpx2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with httpx2.Client(base_url=args.base_url, timeout=120, trust_env=False) as client:
        response = client.get("/v1/water-supply/companies")
        response.raise_for_status()
        index = response.json()
        results = []
        for company in index["items"]:
            response = client.get(
                f"/v1/water-supply/companies/{company['company_acronym']}/geometry",
                params={"snapshot_id": index["snapshot_id"]},
            )
            results.append(
                {
                    "company_acronym": company["company_acronym"],
                    "area_count": company["area_count"],
                    "status": response.status_code,
                    "bytes": len(response.content),
                }
            )
    args.output.write_text(
        json.dumps({"snapshot_id": index["snapshot_id"], "company_responses": results}, indent=2)
        + "\n"
    )


if __name__ == "__main__":
    main()
