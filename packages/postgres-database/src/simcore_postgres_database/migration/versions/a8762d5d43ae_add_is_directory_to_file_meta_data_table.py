"""add_is_directory_to_file_meta_data_table

Revision ID: a8762d5d43ae
Revises: f3285aff5e84
Create Date: 2023-07-10 14:00:48.388395+00:00

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a8762d5d43ae"
down_revision = "f3285aff5e84"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "file_meta_data",
        sa.Column(
            "is_directory",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("file_meta_data", "is_directory")
    # ### end Alembic commands ###