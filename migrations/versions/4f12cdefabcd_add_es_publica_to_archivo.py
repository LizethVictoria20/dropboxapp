"""
add es_publica column to archivo

Revision ID: 4f12cdefabcd
Revises: bf23e45f6789
Create Date: 2025-09-23 10:00:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4f12cdefabcd'
down_revision = 'bf23e45f6789'
branch_labels = None
depends_on = None


def upgrade():
    # Add es_publica column to archivo table with default True
    op.add_column('archivo', sa.Column('es_publica', sa.Boolean(), nullable=True))
    # Set default value for existing rows
    op.execute("UPDATE archivo SET es_publica = 1 WHERE es_publica IS NULL")


def downgrade():
    op.drop_column('archivo', 'es_publica')
