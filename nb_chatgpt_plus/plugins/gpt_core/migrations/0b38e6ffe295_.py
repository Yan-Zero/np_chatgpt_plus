"""empty message

Revision ID: 0b38e6ffe295
Revises: 
Create Date: 2023-04-04 05:15:24.090842

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0b38e6ffe295'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('gpt_core_conversationid',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.String(length=256), nullable=False),
    sa.Column('conversation_id', sa.String(length=256), nullable=False),
    sa.Column('last_time', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('gpt_core_messagerecord',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bot_type', sa.String(length=32), nullable=False),
    sa.Column('bot_id', sa.String(length=64), nullable=False),
    sa.Column('platform', sa.String(length=32), nullable=False),
    sa.Column('time', sa.DateTime(), nullable=False),
    sa.Column('type', sa.String(length=4), nullable=False),
    sa.Column('detail_type', sa.String(length=32), nullable=False),
    sa.Column('message_id', sa.String(length=64), nullable=False),
    sa.Column('message', sa.JSON(), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('group_id', sa.String(length=64), nullable=True),
    sa.Column('quote_id', sa.String(length=64), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('gpt_core_messagerecord')
    op.drop_table('gpt_core_conversationid')
    # ### end Alembic commands ###