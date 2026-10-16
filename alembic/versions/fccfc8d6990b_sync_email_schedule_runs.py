"""sync email_schedule_runs: add lease_id, drop attempts/max_attempts

Revision ID: fccfc8d6990b
Revises: 3046403a40e9
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fccfc8d6990b'
down_revision: Union[str, Sequence[str], None] = '3046403a40e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Las filas previas no tienen lease_id (la tabla era inservible antes de
    # este fix), por lo que se limpian para poder agregar la columna NOT NULL.
    op.execute('DELETE FROM email_schedule_runs')

    op.add_column(
        'email_schedule_runs',
        sa.Column('lease_id', sa.Integer(), nullable=False),
    )
    op.create_index(
        op.f('ix_email_schedule_runs_lease_id'),
        'email_schedule_runs',
        ['lease_id'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_email_schedule_runs_lease_id_leases',
        'email_schedule_runs',
        'leases',
        ['lease_id'],
        ['id'],
        ondelete='CASCADE',
    )

    op.drop_column('email_schedule_runs', 'attempts')
    op.drop_column('email_schedule_runs', 'max_attempts')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'email_schedule_runs',
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
    )
    op.add_column(
        'email_schedule_runs',
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
    )
    op.alter_column('email_schedule_runs', 'max_attempts', server_default=None)
    op.alter_column('email_schedule_runs', 'attempts', server_default=None)

    op.drop_constraint(
        'fk_email_schedule_runs_lease_id_leases',
        'email_schedule_runs',
        type_='foreignkey',
    )
    op.drop_index(
        op.f('ix_email_schedule_runs_lease_id'),
        table_name='email_schedule_runs',
    )
    op.drop_column('email_schedule_runs', 'lease_id')
