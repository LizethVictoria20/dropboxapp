"""Agregar roles

Revision ID: a28966fa3a70
Revises: 3082aa82a8ee
Create Date: 2025-07-14 09:45:45.959368

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a28966fa3a70'
down_revision = '3082aa82a8ee'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rol', sa.String(length=20), nullable=False, server_default='cliente'))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('rol')

    # ### end Alembic commands ###
