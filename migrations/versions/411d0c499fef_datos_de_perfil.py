"""Datos de perfil

Revision ID: 411d0c499fef
Revises: e6661792e40d
Create Date: 2025-07-21 11:40:19.073190

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '411d0c499fef'
down_revision = 'e6661792e40d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('beneficiario', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lastname', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('nationality', sa.String(length=100), nullable=True))

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('nacionality', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('country', sa.String(length=100), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('country')
        batch_op.drop_column('nacionality')

    with op.batch_alter_table('beneficiario', schema=None) as batch_op:
        batch_op.drop_column('nationality')
        batch_op.drop_column('lastname')

    # ### end Alembic commands ###
