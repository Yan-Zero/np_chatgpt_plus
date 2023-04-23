from datetime import datetime, timezone
from typing import Iterable, List, Literal, Optional, Sequence, Union, overload

from nonebot_plugin_datastore import create_session
from sqlalchemy import func, or_, select, delete, desc

from .message import deserialize_message
from .model import MessageRecord
from nonebot.adapters.mirai2 import Bot, SUPERUSER, GroupMessage
from nonebot.adapters.mirai2.event import MessageEvent

import nonebot.log as logger

def remove_timezone(dt: datetime) -> datetime:
    """移除时区"""
    if dt.tzinfo is None:
        return dt
    # 先转至 UTC 时间，再移除时区
    dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)

async def get_message_records(
    *,
    bot_types: Optional[Iterable[str]] = None,
    bot_ids: Optional[Iterable[str]] = None,
    platforms: Optional[Iterable[str]] = None,
    time_start: Optional[datetime] = None,
    time_stop: Optional[datetime] = None,
    types: Optional[Iterable[Literal["message", "message_sent"]]] = None,
    detail_types: Optional[Iterable[str]] = None,
    user_ids: Optional[Iterable[str]] = None,
    group_ids: Optional[Iterable[str]] = None,
    quote_ids: Optional[Iterable[str]] = None,
    exclude_user_ids: Optional[Iterable[str]] = None,
    exclude_group_ids: Optional[Iterable[str]] = None,
    exclude_quote_ids: Optional[Iterable[str]] = None,
) -> Sequence[MessageRecord]:
    """获取消息记录
    参数:
      * ``bot_types: Optional[Iterable[str]]``: 协议适配器类型列表，为空表示所有适配器
      * ``bot_ids: Optional[Iterable[str]]``: bot id 列表，为空表示所有 bot id
      * ``platforms: Optional[Iterable[str]]``: 平台类型列表，为空表示所有平台
      * ``time_start: Optional[datetime]``: 起始时间，UTC 时间，为空表示不限制起始时间
      * ``time_stop: Optional[datetime]``: 结束时间，UTC 时间，为空表示不限制结束时间
      * ``types: Optional[Iterable[Literal["message", "message_sent"]]]``: 消息事件类型列表，为空表示所有类型
      * ``detail_types: Optional[List[str]]``: 消息事件具体类型列表，为空表示所有类型
      * ``user_ids: Optional[Iterable[str]]``: 用户列表，为空表示所有用户
      * ``quote_ids: Optional[Iterable[str]]``: 引用列表，为空表示所有信息
      * ``channel_ids: Optional[Iterable[str]]``: 两级群组消息频道列表，为空表示所有频道
      * ``exclude_user_ids: Optional[Iterable[str]]``: 不包含的用户列表，为空表示不限制
      * ``exclude_group_ids: Optional[Iterable[str]]``: 不包含的群组列表，为空表示不限制
      * ``exclude_quote_ids: Optional[Iterable[str]]``: 不包含的引用列表，为空表示不限制
    返回值:
      * ``List[MessageRecord]``: 消息记录列表
    """

    whereclause = []

    if bot_types:
        whereclause.append(
            or_(*[MessageRecord.bot_type == bot_type for bot_type in bot_types])
        )
    if bot_ids:
        whereclause.append(or_(*[MessageRecord.bot_id == bot_id for bot_id in bot_ids]))
    if platforms:
        whereclause.append(
            or_(*[MessageRecord.platform == platform for platform in platforms])
        )
    if time_start:
        whereclause.append(MessageRecord.time >= remove_timezone(time_start))
    if time_stop:
        whereclause.append(MessageRecord.time <= remove_timezone(time_stop))
    if types:
        whereclause.append(or_(*[MessageRecord.type == type for type in types]))
    if detail_types:
        whereclause.append(
            or_(
                *[
                    MessageRecord.detail_type == detail_type
                    for detail_type in detail_types
                ]
            )
        )
    if user_ids:
        whereclause.append(
            or_(*[MessageRecord.user_id == user_id for user_id in user_ids])
        )
    if group_ids:
        whereclause.append(
            or_(*[MessageRecord.group_id == group_id for group_id in group_ids])
        )
    if quote_ids:
        whereclause.append(
            or_(*[MessageRecord.quote_id == quote_id for quote_id in quote_ids])
        )
    if exclude_user_ids:
        for user_id in exclude_user_ids:
            whereclause.append(MessageRecord.user_id != user_id)
    if exclude_group_ids:
        for group_id in exclude_group_ids:
            whereclause.append(MessageRecord.group_id != group_id)
    if exclude_quote_ids:
        for quote_id in exclude_quote_ids:
            whereclause.append(MessageRecord.quote_id != quote_id)

    statement = select(MessageRecord).where(*whereclause)
    async with create_session() as session:
        records = (await session.scalars(statement)).all()
    return records

async def clear_message_records(
    *,
    bot_types: Optional[Iterable[str]] = None,
    bot_ids: Optional[Iterable[str]] = None,
    platforms: Optional[Iterable[str]] = None,
    time_start: Optional[datetime] = None,
    time_stop: Optional[datetime] = None,
    types: Optional[Iterable[Literal["message", "message_sent"]]] = None,
    detail_types: Optional[Iterable[str]] = None,
    user_ids: Optional[Iterable[str]] = None,
    group_ids: Optional[Iterable[str]] = None,
    quote_ids: Optional[Iterable[str]] = None,
    exclude_user_ids: Optional[Iterable[str]] = None,
    exclude_group_ids: Optional[Iterable[str]] = None,
    exclude_quote_ids: Optional[Iterable[str]] = None,
):
    """清空消息记录
    参数:
      * ``bot_types: Optional[Iterable[str]]``: 协议适配器类型列表，为空表示所有适配器
      * ``bot_ids: Optional[Iterable[str]]``: bot id 列表，为空表示所有 bot id
      * ``platforms: Optional[Iterable[str]]``: 平台类型列表，为空表示所有平台
      * ``time_start: Optional[datetime]``: 起始时间，UTC 时间，为空表示不限制起始时间
      * ``time_stop: Optional[datetime]``: 结束时间，UTC 时间，为空表示不限制结束时间
      * ``types: Optional[Iterable[Literal["message", "message_sent"]]]``: 消息事件类型列表，为空表示所有类型
      * ``detail_types: Optional[List[str]]``: 消息事件具体类型列表，为空表示所有类型
      * ``user_ids: Optional[Iterable[str]]``: 用户列表，为空表示所有用户
      * ``quote_ids: Optional[Iterable[str]]``: 引用列表，为空表示所有信息
      * ``channel_ids: Optional[Iterable[str]]``: 两级群组消息频道列表，为空表示所有频道
      * ``exclude_user_ids: Optional[Iterable[str]]``: 不包含的用户列表，为空表示不限制
      * ``exclude_group_ids: Optional[Iterable[str]]``: 不包含的群组列表，为空表示不限制
      * ``exclude_quote_ids: Optional[Iterable[str]]``: 不包含的引用列表，为空表示不限制
    """

    whereclause = []

    if bot_types:
        whereclause.append(
            or_(*[MessageRecord.bot_type == bot_type for bot_type in bot_types])
        )
    if bot_ids:
        whereclause.append(or_(*[MessageRecord.bot_id == bot_id for bot_id in bot_ids]))
    if platforms:
        whereclause.append(
            or_(*[MessageRecord.platform == platform for platform in platforms])
        )
    if time_start:
        whereclause.append(MessageRecord.time >= remove_timezone(time_start))
    if time_stop:
        whereclause.append(MessageRecord.time <= remove_timezone(time_stop))
    if types:
        whereclause.append(or_(*[MessageRecord.type == type for type in types]))
    if detail_types:
        whereclause.append(
            or_(
                *[
                    MessageRecord.detail_type == detail_type
                    for detail_type in detail_types
                ]
            )
        )
    if user_ids:
        whereclause.append(
            or_(*[MessageRecord.user_id == user_id for user_id in user_ids])
        )
    if group_ids:
        whereclause.append(
            or_(*[MessageRecord.group_id == group_id for group_id in group_ids])
        )
    if quote_ids:
        whereclause.append(
            or_(*[MessageRecord.quote_id == quote_id for quote_id in quote_ids])
        )
    if exclude_user_ids:
        for user_id in exclude_user_ids:
            whereclause.append(MessageRecord.user_id != user_id)
    if exclude_group_ids:
        for group_id in exclude_group_ids:
            whereclause.append(MessageRecord.group_id != group_id)
    if exclude_quote_ids:
        for quote_id in exclude_quote_ids:
            whereclause.append(MessageRecord.quote_id != quote_id)
    
    statement = delete(MessageRecord).where(*whereclause)
    async with create_session() as session:
        await session.execute(statement)

async def del_message_records_to_limit(max_count_per_group: int):
    """删除消息记录，使每个群组的消息记录数不超过 `max_count_per_group`
    参数:
      * ``max_count_per_group: int``: 每个群组的最大消息记录数
    """

    async def delete_records_by_key(session, key, key_value):
        count = int(key_value[1])
        statement = (
            select(MessageRecord.id)
            .where(getattr(MessageRecord, key) == key_value[0])
            .order_by(MessageRecord.time.asc())
            .limit(count - max_count_per_group)
        )
        ids = (await session.scalars(statement)).all()
        statement = delete(MessageRecord).where(MessageRecord.id.in_(ids))
        await session.execute(statement)
        await session.commit()

    async with create_session() as session:
        statement = (
            select(MessageRecord.group_id, func.count(MessageRecord.id).label("count"))
            .group_by(MessageRecord.group_id)
            .having(func.count(MessageRecord.id) > max_count_per_group)
        )
        records= (await session.scalars(statement)).all()
    for record in records:
        if record is None or record[0] is None:
            continue
        await delete_records_by_key(session, 'group_id', record)
    logger.logger.info(f"删除了 {len(records)} 个群组的消息记录")

    statement = (
        select(MessageRecord.user_id, func.count(MessageRecord.id).label("count"))
        .where(MessageRecord.group_id == None)
        .group_by(MessageRecord.user_id)
        .having(func.count(MessageRecord.id) > max_count_per_group)
    )
    records = (await session.scalars(statement)).all()
    for record in records:
        if record is None:
            continue
        await delete_records_by_key(session, 'user_id', record)
    logger.logger.info(f"删除了 {len(records)} 个用户的消息记录")


async def del_all_message_records():
    """删除所有消息记录
    """
    async with create_session() as session:
        await session.execute(delete(MessageRecord))
        await session.commit()

# async def get_messages(bot: Bot, **kwargs) -> List[MessageEvent]:
#     """获取消息记录的消息列表
#     参数:
#       * ``bot: Union[V11Bot, V12Bot]``: Nonebot `Bot` 对象，用于判断消息类型
#       * ``**kwargs``: 筛选参数，具体查看 `get_message_records` 中的定义
#     返回值:
#       * ``Union[List[V11Msg], List[V12Msg]]``: 消息列表
#     """
#     kwargs.update({"bot_types": [bot.adapter.get_name()]})
#     records = await get_message_records(**kwargs)
#     # return [deserialize_message(record.message, V12Msg) for record in records]
#     return [ for record in records]
