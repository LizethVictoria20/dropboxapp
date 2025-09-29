"""add cargo to user

Revision ID: 7b1a2c3d4e5f
Revises: 69b8a78150b4
Create Date: 2025-09-29 17:25:33.861724

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7b1a2c3d4e5f'
down_revision = '69b8a78150b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cargo', sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('cargo')
