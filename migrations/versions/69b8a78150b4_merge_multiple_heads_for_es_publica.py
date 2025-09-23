"""merge multiple heads for es_publica

Revision ID: 69b8a78150b4
Revises: 14c00cd21ea9, 3aaf4042c216, 4f12cdefabcd
Create Date: 2025-09-23 16:18:15.610045

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '69b8a78150b4'
down_revision = ('14c00cd21ea9', '3aaf4042c216', '4f12cdefabcd')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
