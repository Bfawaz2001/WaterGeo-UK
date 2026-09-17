"""All database tests require explicit opt-in, including future modules."""

import os

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" not in item.path.parts:
            continue
        item.add_marker(pytest.mark.integration)
        if os.environ.get("WATERGEO_TEST_DATABASE") != "1":
            item.add_marker(
                pytest.mark.skip(
                    reason="Set WATERGEO_TEST_DATABASE=1 with a disposable PostGIS database"
                )
            )
