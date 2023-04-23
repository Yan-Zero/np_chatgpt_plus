import nonebot, datetime, httpx, nonebot.plugin, nonebot.rule, traceback
from nonebot.adapters.mirai2 import (
    Bot,
    SUPERUSER,
    GroupMessage,
    FriendMessage,
    MessageChain,
)
from nonebot.adapters.mirai2.event import MessageEvent, Event
from nonebot_plugin_datastore import get_plugin_data, create_session
from .config import Config
from ..gpt_core.record import (
    del_message_records_to_limit,
    clear_message_records,
    del_all_message_records,
    get_message_records,
)
from ..gpt_core import handle_clear_record
from .summarize import summarize_message


summarize = nonebot.plugin.on_command(
    "sum",
    rule=nonebot.rule.to_me(),
    aliases={"summarize"},
    priority=9,
    block=True,
    permission=SUPERUSER,
)
global_config = nonebot.get_driver().config
plugin_config = Config.parse_obj(global_config)
plugin_data = get_plugin_data()


@summarize.handle()
async def handle_summarize(bot: Bot, event: MessageEvent):
    await summarize.send("正在处理，请稍后...")

    t = (
        await plugin_data.config.get("last_clear_time")
        or datetime.datetime.utcnow().timestamp()
    )
    if (datetime.datetime.utcnow() - datetime.datetime.utcfromtimestamp(t)).days > 0:
        await plugin_data.config.set(
            "last_clear_time", datetime.datetime.utcnow().timestamp()
        )
        await handle_clear_record(bot, event, "")

    if isinstance(event, GroupMessage):
        records = await get_message_records(
            group_ids=[str(event.sender.group.id)],
            time_start=datetime.datetime.utcnow() - datetime.timedelta(days=1),
        )
    elif isinstance(event, FriendMessage):
        records = await get_message_records(
            user_ids=[str(event.sender.id)],
            detail_types=["friend", "others"],
            time_start=datetime.datetime.utcnow() - datetime.timedelta(days=1),
        )
    else:
        return
    try:
        result = await summarize_message(bot, records)
        await summarize.send(result)
        return
    except Exception as e:
        if isinstance(e, TimeoutError):
            await summarize.finish("请求超时，请稍后再试")
        elif isinstance(e, httpx.HTTPStatusError):
            print(traceback.format_exc())
            if e.response.status_code == 429:
                await summarize.finish("请求过于频繁，请稍后再试")
            else:
                await summarize.finish(f"错误代码：{e.response.status_code}\n错误信息：{e}")
        else:
            await summarize.send("未知错误，请稍后再试：\n{e}\n{eargs}".format(e=e, eargs=e.args))
            raise e
