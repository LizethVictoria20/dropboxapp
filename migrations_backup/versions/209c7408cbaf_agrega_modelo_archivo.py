"""Agrega modelo Archivo

Revision ID: 209c7408cbaf
Revises: 5ea6441ab1cb
Create Date: 2025-07-12 09:02:11.128142

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '209c7408cbaf'
down_revision = '5ea6441ab1cb'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('archivo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=255), nullable=False),
    sa.Column('categoria', sa.String(length=100), nullable=False),
    sa.Column('subcategoria', sa.String(length=100), nullable=False),
    sa.Column('dropbox_path', sa.String(length=500), nullable=False),
    sa.Column('fecha_subida', sa.DateTime(), nullable=True),
    sa.Column('tamano', sa.Integer(), nullable=True),
    sa.Column('extension', sa.String(length=20), nullable=True),
    sa.Column('descripcion', sa.String(length=255), nullable=True),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['usuario_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('archivo')
    # ### end Alembic commands ###
