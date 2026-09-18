"""Request-scoped access to the application's read-only database engine."""

from typing import cast

from fastapi import Request
from sqlalchemy import Engine


def get_database(request: Request) -> Engine:
    return cast(Engine, request.app.state.database)
