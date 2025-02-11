"""new icon table

Revision ID: 3fe27ff48f73
Revises: 611f956aa3e3
Create Date: 2025-02-05 16:50:02.419293+00:00

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3fe27ff48f73"
down_revision = "611f956aa3e3"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("services_meta_data", sa.Column("icon", sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("services_meta_data", "icon")
    # ### end Alembic commands ###
