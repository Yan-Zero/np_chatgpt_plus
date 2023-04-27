from datetime import datetime
from nonebot_plugin_datastore import get_plugin_data
from sqlalchemy import JSON, TEXT, String, Integer
from sqlalchemy.orm import Mapped, mapped_column

Model = get_plugin_data().Model


class ConversationId(Model):
    """会话id"""

    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(256), unique=True)
    """ 用户id """
    conversation_id: Mapped[str] = mapped_column(String(256))
    """ 会话id """
    last_time: Mapped[datetime]
    """ 最后一次使用时间 """

    def __repr__(self):
        return f"<ConversationId {self.id}>[{self.__dict__}]"

    def __str__(self):
        return f"<ConversationId {self.id}>[{self.__dict__}]"
