from io import BytesIO
from typing import Any

import pytest

from watergeo.operations import evidence_bucket


class FakeClient:
    def __init__(self) -> None:
        self.versioning = "Enabled"
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_bucket_versioning(self, **kwargs: Any) -> None:
        self.versioning = kwargs["VersioningConfiguration"]["Status"]

    def get_bucket_versioning(self, **kwargs: Any) -> dict[str, str]:
        return {"Status": self.versioning}

    def get_bucket_acl(self, **kwargs: Any) -> dict[str, list[object]]:
        return {"Grants": []}

    def put_object(self, **kwargs: Any) -> dict[str, str]:
        self.objects[(kwargs["Key"], "version-1")] = kwargs["Body"]
        self.metadata = kwargs["Metadata"]
        return {"VersionId": "version-1"}

    def get_object(self, **kwargs: Any) -> dict[str, object]:
        return {
            "Body": BytesIO(self.objects[(kwargs["Key"], kwargs["VersionId"])]),
            "Metadata": self.metadata,
        }

    def delete_object(self, **kwargs: Any) -> None:
        del self.objects[(kwargs["Key"], kwargs["VersionId"])]


def environment(*, administrator: bool) -> dict[str, str]:
    prefix = "WATERGEO_SPACES_ADMIN" if administrator else "WATERGEO_EVIDENCE_S3"
    return {
        "WATERGEO_EVIDENCE_S3_ENDPOINT": "https://lon1.digitaloceanspaces.com",
        "WATERGEO_EVIDENCE_S3_REGION": "lon1",
        "WATERGEO_EVIDENCE_S3_BUCKET": "watergeo-evidence-example",
        f"{prefix}_ACCESS_KEY_ID": "access-key",
        f"{prefix}_SECRET_ACCESS_KEY": "secret-key",
    }


def test_configure_enables_versioning_and_checks_private_acl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    client.versioning = "Suspended"
    monkeypatch.setattr(evidence_bucket, "_client", lambda settings: client)
    evidence_bucket.configure_and_verify(environment(administrator=True))
    assert client.versioning == "Enabled"


def test_operator_check_reads_back_then_deletes_only_its_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    monkeypatch.setattr(evidence_bucket, "_client", lambda settings: client)
    evidence_bucket.verify_operator_access(environment(administrator=False))
    assert client.objects == {}


def test_endpoint_must_match_selected_region() -> None:
    values = environment(administrator=False)
    values["WATERGEO_EVIDENCE_S3_ENDPOINT"] = "https://fra1.digitaloceanspaces.com"
    with pytest.raises(ValueError, match="exactly match"):
        evidence_bucket.BucketSettings.from_environment(values, administrator=False)
