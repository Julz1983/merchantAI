"""initial tenancy schema: merchants, users, api_keys + RLS

Revision ID: 0001
Revises:
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')  # gen_random_uuid()

    # ── merchants: the tenant root. Not RLS-protected itself — every access
    # pattern in the app looks it up by a single known id (from the JWT or a
    # signed-up user's own record), never by an unscoped list query. ────────
    op.create_table(
        "merchants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("logo_url", sa.String(1024), nullable=True),
        sa.Column("brand_colors", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("ai_persona", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="trial"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── users ────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_merchant_id", "users", ["merchant_id"])

    # ── api_keys ─────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_merchant_id", "api_keys", ["merchant_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    # ── Row-Level Security ──────────────────────────────────────────────
    # Enforcement point described in architecture §13: even if application code
    # forgets a WHERE merchant_id = ... filter, Postgres blocks cross-tenant
    # rows at the database layer. FORCE RLS so even the table owner (the app's
    # DB role) is subject to the policy, not just other roles.
    #
    # SELECT policy has a deliberate carve-out: current_setting(...) returns ''
    # when no tenant context has been set for the session (i.e. during login,
    # which runs on the unscoped get_db session — see core/tenancy.py). That
    # path is the one legitimate case where the app needs to look a user up
    # by email *before* it knows which merchant they belong to. INSERT/UPDATE/
    # DELETE have no such carve-out — writes always require a matching tenant
    # context.
    for table in ("users", "api_keys"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        op.execute(
            f"""
            CREATE POLICY {table}_tenant_select ON {table}
            FOR SELECT
            USING (
                merchant_id::text = current_setting('app.current_merchant_id', true)
                OR current_setting('app.current_merchant_id', true) = ''
            )
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_write ON {table}
            FOR INSERT
            WITH CHECK (merchant_id::text = current_setting('app.current_merchant_id', true))
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_update ON {table}
            FOR UPDATE
            USING (merchant_id::text = current_setting('app.current_merchant_id', true))
            WITH CHECK (merchant_id::text = current_setting('app.current_merchant_id', true))
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_delete ON {table}
            FOR DELETE
            USING (merchant_id::text = current_setting('app.current_merchant_id', true))
            """
        )


def downgrade() -> None:
    for table in ("users", "api_keys"):
        for policy in ("select", "write", "update", "delete"):
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_{policy} ON {table}")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("merchants")
