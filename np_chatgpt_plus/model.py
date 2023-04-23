from datetime import datetime
from typing import Optional, List, Dict, Any

from nonebot_plugin_datastore import get_plugin_data
from sqlalchemy import JSON, TEXT, String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from nonebot.adapters.mirai2.message import MessageChain

JsonMsg = List[Dict[str, Any]]

Model = get_plugin_data().Model


def deserialize_message(msg: JsonMsg):
    return MessageChain(msg)


class ConversationId(Model):
    """会话id"""

    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(256))
    """ 用户id """
    conversation_id: Mapped[str] = mapped_column(String(256))
    """ 会话id """
    last_time: Mapped[datetime]
    """ 最后一次使用时间 """

    def __repr__(self):
        return f"<ConversationId {self.id}>[{self.__dict__}]"

    def __str__(self):
        return f"<ConversationId {self.id}>[{self.__dict__}]"


class MessageRecord(Model):
    """消息记录"""

    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_type: Mapped[str] = mapped_column(String(32))
    """ 协议适配器名称 """
    bot_id: Mapped[str] = mapped_column(String(64))
    """ 机器人id """
    platform: Mapped[str] = mapped_column(String(32))
    """ 机器人平台名称 """
    time: Mapped[datetime]
    """ 消息时间"""
    type: Mapped[str] = mapped_column(String(4))
    """ 事件类型\n\n此处主要包含 `s` 和 `r` 两种\n\n`s` 是 bot 发出的消息"""
    detail_type: Mapped[str] = mapped_column(String(32))
    """ 具体事件类型 """
    message_id: Mapped[str] = mapped_column(String(64))
    """ 消息id """
    message: Mapped[JsonMsg] = mapped_column(JSON)
    """ 消息内容 """
    user_id: Mapped[str] = mapped_column(String(64))
    """ 用户id """
    group_id: Mapped[Optional[str]] = mapped_column(String(64))
    """ 群组id """
    quote_id: Mapped[Optional[str]] = mapped_column(String(64))

    def __repr__(self):
        return f"<MessageRecord {self.id}>[{self.__dict__}]"

    def __str__(self):
        return f"<MessageRecord {self.id}>[{self.__dict__}]"
