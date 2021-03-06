"""new services_consume_filetype table

Revision ID: e43bd59a8e17
Revises: e6df5998cc74
Create Date: 2021-03-02 14:57:19.527779+00:00

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e43bd59a8e17"
down_revision = "e6df5998cc74"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "services_consume_filetypes",
        sa.Column("service_key", sa.String(), nullable=False),
        sa.Column("service_version", sa.String(), nullable=False),
        sa.Column("service_display_name", sa.String(), nullable=False),
        sa.Column("service_input_port", sa.String(), nullable=False),
        sa.Column("filetype", sa.String(), nullable=False),
        sa.Column("preference_order", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["service_key", "service_version"],
            ["services_meta_data.key", "services_meta_data.version"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "service_key",
            "service_version",
            "filetype",
            name="services_consume_filetypes_pk",
        ),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("services_consume_filetypes")
    # ### end Alembic commands ###
