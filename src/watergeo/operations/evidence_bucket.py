"""Configure and verify a private, versioned Spaces evidence bucket."""

import argparse
import hashlib
import importlib
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class BucketSettings:
    endpoint: str
    region: str
    bucket: str
    access_key_id: str
    secret_access_key: str

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str], *, administrator: bool
    ) -> "BucketSettings":
        credential_prefix = "WATERGEO_SPACES_ADMIN" if administrator else "WATERGEO_EVIDENCE_S3"
        names = {
            "endpoint": "WATERGEO_EVIDENCE_S3_ENDPOINT",
            "region": "WATERGEO_EVIDENCE_S3_REGION",
            "bucket": "WATERGEO_EVIDENCE_S3_BUCKET",
            "access_key_id": f"{credential_prefix}_ACCESS_KEY_ID",
            "secret_access_key": f"{credential_prefix}_SECRET_ACCESS_KEY",
        }
        missing = [name for name in names.values() if not environment.get(name)]
        if missing:
            raise ValueError("Missing required environment names: " + ", ".join(missing))
        region = environment[names["region"]]
        endpoint = environment[names["endpoint"]].rstrip("/")
        if endpoint != f"https://{region}.digitaloceanspaces.com":
            raise ValueError("Spaces endpoint must exactly match the selected regional endpoint")
        return cls(**{field: environment[name] for field, name in names.items()})


def _client(settings: BucketSettings) -> Any:
    boto3 = importlib.import_module("boto3")
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint,
        region_name=settings.region,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.secret_access_key,
    )


def configure_and_verify(environment: Mapping[str, str]) -> None:
    settings = BucketSettings.from_environment(environment, administrator=True)
    client = _client(settings)
    client.put_bucket_versioning(
        Bucket=settings.bucket,
        VersioningConfiguration={"Status": "Enabled"},
    )
    status = client.get_bucket_versioning(Bucket=settings.bucket)
    if status.get("Status") != "Enabled":
        raise RuntimeError("Spaces bucket versioning is not enabled")
    acl = client.get_bucket_acl(Bucket=settings.bucket)
    public_uris = {
        "http://acs.amazonaws.com/groups/global/AllUsers",
        "http://acs.amazonaws.com/groups/global/AuthenticatedUsers",
    }
    if any(grant.get("Grantee", {}).get("URI") in public_uris for grant in acl.get("Grants", [])):
        raise RuntimeError("Spaces bucket ACL grants public access")


def verify_operator_access(environment: Mapping[str, str]) -> None:
    settings = BucketSettings.from_environment(environment, administrator=False)
    client = _client(settings)
    status = client.get_bucket_versioning(Bucket=settings.bucket)
    if status.get("Status") != "Enabled":
        raise RuntimeError("Spaces bucket versioning is not enabled")
    body = f"watergeo evidence verification {datetime.now(UTC).isoformat()}\n".encode()
    digest = hashlib.sha256(body).hexdigest()
    key = f"watergeo/evidence/.verification/{uuid4()}.txt"
    uploaded = client.put_object(
        Bucket=settings.bucket,
        Key=key,
        Body=body,
        Metadata={"sha256": digest},
    )
    version_id = uploaded.get("VersionId")
    if not version_id:
        raise RuntimeError("Spaces did not return a version ID for the test object")
    try:
        response = client.get_object(Bucket=settings.bucket, Key=key, VersionId=version_id)
        returned = response["Body"].read()
        if returned != body or response.get("Metadata", {}).get("sha256") != digest:
            raise RuntimeError("Spaces test object readback did not match")
    finally:
        client.delete_object(Bucket=settings.bucket, Key=key, VersionId=version_id)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("configure", "verify-operator"))
    arguments = parser.parse_args(argv)
    if arguments.action == "configure":
        configure_and_verify(os.environ)
    else:
        verify_operator_access(os.environ)
    print(f"Evidence bucket {arguments.action} completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
