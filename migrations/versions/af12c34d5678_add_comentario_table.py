"""add comentario table

Revision ID: af12c34d5678
Revises: 98730ad8a261
Create Date: 2025-09-12 00:00:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'af12c34d5678'
down_revision = '98730ad8a261'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'comentario',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('dropbox_path', sa.String(length=500), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False, server_default='archivo'),
        sa.Column('contenido', sa.Text(), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_comentario_dropbox_path', 'comentario', ['dropbox_path'], unique=False)


def downgrade():
    op.drop_index('ix_comentario_dropbox_path', table_name='comentario')
    op.drop_table('comentario')


