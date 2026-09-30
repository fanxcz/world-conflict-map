"""Initial tables + PostGIS enable (postgres only)."""
from alembic import op
import sqlalchemy as sa

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables are created via Base.metadata.create_all for portability (sqlite + postgres).
    # This migration enables PostGIS when running on PostgreSQL and adds GIST indexes.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        op.execute("CREATE INDEX IF NOT EXISTS ix_events_geo ON events (longitude, latitude);")
        op.execute("CREATE INDEX IF NOT EXISTS ix_conflicts_updated ON conflicts (last_updated);")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_events_geo;")
        op.execute("DROP INDEX IF EXISTS ix_conflicts_updated;")
