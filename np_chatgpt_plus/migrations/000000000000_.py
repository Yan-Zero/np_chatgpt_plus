from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "000000000000"
down_revision = "1dd00de86fc2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 把 np_chatgpt_plus_conversationid 表改名为 np_chatgpt_plus_userinfo
    op.alter_column("np_chatgpt_plus_conversationid", "conversation_id", nullable=True)
    op.rename_table("np_chatgpt_plus_conversationid", "np_chatgpt_plus_userinfo")
    op.add_column(
        "np_chatgpt_plus_userinfo",
        sa.Column("platform", sa.String(256), nullable=True),
    )
    op.execute("UPDATE np_chatgpt_plus_userinfo SET platform = 'OneBot V11'")
    op.alter_column("np_chatgpt_plus_userinfo", "platform", nullable=False)
    op.rename_table(
        "np_chatgpt_plus_conversationid_id_seq", "np_chatgpt_plus_userinfo_id_seq"
    )


def downgrade() -> None:
    op.drop_column("np_chatgpt_plus_userinfo", "platform")
    op.rename_table("np_chatgpt_plus_userinfo", "np_chatgpt_plus_conversationid")
    op.execute(
        "UPDATE np_chatgpt_plus_conversationid SET conversation_id = '' WHERE conversation_id IS NULL"
    )
    op.alter_column("np_chatgpt_plus_conversationid", "conversation_id", nullable=False)
    op.rename_table(
        "np_chatgpt_plus_userinfo_id_seq", "np_chatgpt_plus_conversationid_id_seq"
    )
