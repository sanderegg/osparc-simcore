"""add restriction ondelete

Revision ID: d84edab53761
Revises: 163b11424cb1
Create Date: 2025-02-25 09:18:14.541874+00:00

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "d84edab53761"
down_revision = "163b11424cb1"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint(
        "uq_licensed_item_to_resource_resource_id",
        "licensed_item_to_resource",
        ["licensed_resource_id"],
    )
    op.drop_constraint(
        "fk_rut_pricing_plan_to_service_key_and_version",
        "resource_tracker_pricing_plan_to_service",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_rut_pricing_plan_to_service_key_and_version",
        "resource_tracker_pricing_plan_to_service",
        "services_meta_data",
        ["service_key", "service_version"],
        ["key", "version"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(
        "fk_rut_pricing_plan_to_service_key_and_version",
        "resource_tracker_pricing_plan_to_service",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_rut_pricing_plan_to_service_key_and_version",
        "resource_tracker_pricing_plan_to_service",
        "services_meta_data",
        ["service_key", "service_version"],
        ["key", "version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "uq_licensed_item_to_resource_resource_id",
        "licensed_item_to_resource",
        type_="unique",
    )
    # ### end Alembic commands ###
