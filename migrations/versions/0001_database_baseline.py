"""Verify provisioned PostGIS and establish the initial schema revision.

Roles, the extension, and the empty watergeo schema are administrator-provisioned.
There are deliberately no domain tables before the first source investigation.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SELECT public.PostGIS_Version()")


def downgrade() -> None:
    """Alembic removes the revision; administrator-owned infrastructure stays intact."""
