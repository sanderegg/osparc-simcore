"""modify licensed items/resources DB

Revision ID: a53c3c153bc8
Revises: 78f24aaf3f78
Create Date: 2025-02-13 10:13:32.817207+00:00

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a53c3c153bc8"
down_revision = "78f24aaf3f78"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "licensed_item_to_resource",
        sa.Column("licensed_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "licensed_resource_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "created",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "modified",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["licensed_item_id"],
            ["licensed_items.licensed_item_id"],
            name="fk_licensed_item_to_resource_licensed_item_id",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["licensed_resource_id"],
            ["licensed_resources.licensed_resource_id"],
            name="fk_licensed_item_to_resource_licensed_resource_id",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )
    op.add_column("licensed_items", sa.Column("key", sa.String(), nullable=False))
    op.add_column("licensed_items", sa.Column("version", sa.String(), nullable=False))
    op.alter_column(
        "licensed_items", "pricing_plan_id", existing_type=sa.BIGINT(), nullable=False
    )
    op.alter_column(
        "licensed_items", "product_name", existing_type=sa.VARCHAR(), nullable=False
    )
    op.drop_constraint(
        "uq_licensed_resource_name_type", "licensed_items", type_="unique"
    )
    op.create_index(
        "idx_licensed_items_key_version",
        "licensed_items",
        ["key", "version"],
        unique=True,
    )
    op.drop_column("licensed_items", "licensed_resource_data")
    op.drop_column("licensed_items", "trashed")
    op.drop_column("licensed_items", "licensed_resource_name")
    op.add_column(
        "resource_tracker_licensed_items_checkouts",
        sa.Column("key", sa.String(), nullable=False),
    )
    op.add_column(
        "resource_tracker_licensed_items_checkouts",
        sa.Column("version", sa.String(), nullable=False),
    )
    op.create_index(
        "idx_licensed_items_checkouts_key_version",
        "resource_tracker_licensed_items_checkouts",
        ["key", "version"],
        unique=False,
    )
    op.add_column(
        "resource_tracker_licensed_items_purchases",
        sa.Column("key", sa.String(), nullable=False),
    )
    op.add_column(
        "resource_tracker_licensed_items_purchases",
        sa.Column("version", sa.String(), nullable=False),
    )
    op.create_index(
        "idx_licensed_items_purchases_key_version",
        "resource_tracker_licensed_items_purchases",
        ["key", "version"],
        unique=False,
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        "idx_licensed_items_purchases_key_version",
        table_name="resource_tracker_licensed_items_purchases",
    )
    op.drop_column("resource_tracker_licensed_items_purchases", "version")
    op.drop_column("resource_tracker_licensed_items_purchases", "key")
    op.drop_index(
        "idx_licensed_items_checkouts_key_version",
        table_name="resource_tracker_licensed_items_checkouts",
    )
    op.drop_column("resource_tracker_licensed_items_checkouts", "version")
    op.drop_column("resource_tracker_licensed_items_checkouts", "key")
    op.add_column(
        "licensed_items",
        sa.Column(
            "licensed_resource_name", sa.VARCHAR(), autoincrement=False, nullable=False
        ),
    )
    op.add_column(
        "licensed_items",
        sa.Column(
            "trashed",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
            comment="The date and time when the licensed_item was marked as trashed. Null if the licensed_item has not been trashed [default].",
        ),
    )
    op.add_column(
        "licensed_items",
        sa.Column(
            "licensed_resource_data",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=True,
        ),
    )
    op.drop_index("idx_licensed_items_key_version", table_name="licensed_items")
    op.create_unique_constraint(
        "uq_licensed_resource_name_type",
        "licensed_items",
        ["licensed_resource_name", "licensed_resource_type"],
    )
    op.alter_column(
        "licensed_items", "product_name", existing_type=sa.VARCHAR(), nullable=True
    )
    op.alter_column(
        "licensed_items", "pricing_plan_id", existing_type=sa.BIGINT(), nullable=True
    )
    op.drop_column("licensed_items", "version")
    op.drop_column("licensed_items", "key")
    op.drop_table("licensed_item_to_resource")
    # ### end Alembic commands ###
