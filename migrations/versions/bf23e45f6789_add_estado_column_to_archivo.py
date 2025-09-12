"""add estado column to archivo

Revision ID: bf23e45f6789
Revises: af12c34d5678
Create Date: 2025-09-12 12:00:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'bf23e45f6789'
down_revision = 'af12c34d5678'
branch_labels = None
depends_on = None


def upgrade():
    # Add estado column to archivo table
    op.add_column('archivo', sa.Column('estado', sa.String(length=20), nullable=True))
    
    # Update existing records to have 'en_revision' as default state
    op.execute("UPDATE archivo SET estado = 'en_revision' WHERE estado IS NULL")


def downgrade():
    op.drop_column('archivo', 'estado')
