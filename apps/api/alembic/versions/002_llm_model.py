"""Add llm_model to generation_runs.

Revision ID: 002_llm_model
Revises: 001_initial
Create Date: 2026-11-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_llm_model"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generation_runs",
        sa.Column("llm_model", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generation_runs", "llm_model")
