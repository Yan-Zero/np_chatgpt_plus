from typing import Dict, List, Any, Union
from time import time
import asyncio

from nonebot import on_notice, on_command
from nonebot.adapters.onebot.v11 import (
    Adapter,
    Bot,
    Event,
    MessageEvent,
    Message,
    MessageSegment,
    NoticeEvent,
    GroupRecallNoticeEvent,
    FriendRecallNoticeEvent,
)
from nonebot.log import logger
from nonebot.exception import ActionFailed
from nonebot.adapters.onebot.v11.utils import escape
from nonebot.permission import SUPERUSER

from nonebot_plugin_apscheduler import scheduler


msg_id_for_sender: Dict[int, List[int]] = {}
"""
对应关系 
    发送者的消息id: [事件时间戳，机器人发送的消息的消息id列表...]
"""


def save_msg_id(event: MessageEvent, result: Dict[str, Any]):
    try:
        logger.info(f"保存对应关系：{event} => {result}")
        if msg_id_for_sender.get(event.message_id):
            msg_id_for_sender[event.message_id].append(result["message_id"])
        else:
            msg_id_for_sender[event.message_id] = [event.time, result["message_id"]]
    except KeyError:
        logger.error(f"保存对应关系时发生错误，KeyError：{event} => {result}")

    return result


async def c_send(
    bot: "Bot",
    event: Event,
    message: Union[str, Message, MessageSegment],
    at_sender: bool = False,
    reply_message: bool = False,
    **params: Any,  # extra options passed to send_msg API
):
    """默认回复消息处理函数。"""
    event_dict = event.dict()

    if "message_id" not in event_dict:
        reply_message = False  # if no message_id, force disable reply_message

    if "user_id" in event_dict:  # copy the user_id to the API params if exists
        params.setdefault("user_id", event_dict["user_id"])
    else:
        at_sender = False  # if no user_id, force disable at_sender

    if "group_id" in event_dict:  # copy the group_id to the API params if exists
        params.setdefault("group_id", event_dict["group_id"])

    if "message_type" not in params:  # guess the message_type
        if params.get("group_id") is not None:
            params["message_type"] = "group"
        elif params.get("user_id") is not None:
            params["message_type"] = "private"
        else:
            raise ValueError("Cannot guess message type to reply!")

    full_message = Message()  # create a new message with at sender segment
    if reply_message:
        full_message += MessageSegment.reply(event_dict["message_id"])
    if at_sender and params["message_type"] != "private":
        full_message += MessageSegment.at(params["user_id"]) + " "
    full_message += message
    params.setdefault("message", full_message)

    res = await bot.send_msg(**params)
    if isinstance(event, MessageEvent):
        save_msg_id(event, res)
    return res


Adapter.custom_send(c_send)


async def is_recall(event: NoticeEvent):
    return isinstance(event, (GroupRecallNoticeEvent, FriendRecallNoticeEvent))


auto_recall = on_notice(rule=is_recall, block=False, priority=1)


@auto_recall.handle()
async def _(bot: Bot, event: NoticeEvent):
    if msg_ids := msg_id_for_sender.get(event.message_id):
        del msg_ids[0] # 删除时间戳
        for msg_id in msg_ids:
            try:
                await bot.delete_msg(message_id=msg_id)
            except ActionFailed:
                logger.warning(f"撤回消息 {msg_id} 失败")
            await asyncio.sleep(1)
        del msg_id_for_sender[event.message_id]  # 撤回后清理无效记录


@scheduler.scheduled_job("interval", hours=1)
async def clean_dict():
    """
    隔一个小时清一下
    """

    for k in tuple(msg_id_for_sender.keys()):
        if time() - msg_id_for_sender[k][0] > 1800:
            del msg_id_for_sender[k]

    logger.warning(f"已清理消息id对应表中过期消息，当前记录数：{len(msg_id_for_sender)}")
