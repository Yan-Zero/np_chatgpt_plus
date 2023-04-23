import nonebot

nonebot.require("nonebot_plugin_datastore")
import nonebot.plugin, nonebot.rule
import httpx, nonebot, datetime
from nonebot.adapters.mirai2 import (
    Bot,
    SUPERUSER,
    GroupMessage,
    FriendMessage,
    MessageChain,
)
from nonebot.adapters.mirai2.event import MessageEvent, Event
from nonebot.adapters import Bot as BaseBot
from nonebot.adapters.mirai2.message import MessageType, MessageSegment
from nonebot.params import CommandArg, Command
from nonebot_plugin_datastore import get_plugin_data, create_session
from nonebot.message import event_postprocessor
from typing import Optional, Dict, Any
from nonebot_plugin_datastore.db import post_db_init
from sqlalchemy import func, or_, select, delete, desc
from .rule import BAN, COUNT_LIMIT, GPTOWNER
from .model import MessageRecord, ConversationId
from .gpt_core import GPTCore
from revChatGPT.typings import Error as CBTError
from .gpt_core.record import (
    remove_timezone,
    get_message_records,
    del_message_records_to_limit,
    clear_message_records,
    del_all_message_records,
)
from .gpt_core.api_handle import user_api_manager
from .config import Config


global_config = nonebot.get_driver().config
plugin_config = Config.parse_obj(global_config)
plugin_data = get_plugin_data()
cbt_config = {
    # "proxy": plugin_config.proxy,
    "paid": plugin_config.paid,
    "access_token": plugin_config.access_token,
    "model": plugin_config.model,
}
if plugin_config.proxy:
    cbt_config["proxy"] = plugin_config.proxy
if plugin_config.cf_clearance:
    if not plugin_config.cf_clearance_ua:
        raise ValueError("cf_clearance_ua is required.")
    cbt_config["cf_clearance_ua"] = plugin_config.cf_clearance_ua
    cbt_config["cf_clearance"] = plugin_config.cf_clearance
GPTCORE = GPTCore(cbt_config, plugin_config, "苦咖啡")
API_HANDLE = GPTCORE.cbt.recipients


@post_db_init
async def init_db():
    await GPTCORE.load_user_cid()


clear_record = nonebot.plugin.on_command(
    "clear",
    rule=nonebot.rule.to_me(),
    aliases={"clear_record"},
    priority=9,
    block=True,
    permission=SUPERUSER,
)
chatbot = nonebot.plugin.on_command("chat", priority=15, block=True)
reset = nonebot.plugin.on_command(
    "reset", aliases={"reset_chatgpt", "rc"}, priority=10, block=True
)
gpt4 = nonebot.on_command(
    "gpt-4", aliases={"gpt4"}, priority=10, block=True, permission=GPTOWNER
)
set_ = nonebot.on_command("set", priority=10, block=True, permission=SUPERUSER)
was_mention = nonebot.on_message(rule=nonebot.rule.to_me(), priority=49, block=True)
was_call = nonebot.on_message(rule=nonebot.rule.keyword("苦咖啡"), priority=50, block=True)
manage = nonebot.plugin.on_command(
    ("chat", "open"),
    rule=nonebot.rule.to_me(),
    aliases={("chat", "close")},
    permission=SUPERUSER,
    block=True,
)
api_docs = nonebot.on_command("api", priority=10, block=True)
rule_ = nonebot.on_command("ban", priority=10, block=True, permission=GPTOWNER)
unban = nonebot.on_command("unban", priority=10, block=True, permission=GPTOWNER)


@rule_.handle()
async def handle_ban(bot: Bot, event: MessageEvent, args: MessageChain = CommandArg()):
    if not args:
        await rule_.finish("参数错误")
    lists = [str(x.data["target"]) for x in args if x.type == MessageType.AT]
    lists.extend([x for x in args.extract_plain_text().split(" ") if x.isdigit()])
    lists = set(lists)
    lists.update(await plugin_data.config.get("ban", set()))
    await plugin_data.config.set("ban", list(lists))
    await rule_.finish(f"已封禁: {', '.join(lists)}")


@unban.handle()
async def handle_unban(
    bot: Bot, event: MessageEvent, args: MessageChain = CommandArg()
):
    if not args:
        await unban.finish("参数错误")
    lists = [str(x.data["target"]) for x in args if x.type == MessageType.AT]
    lists.extend([x for x in args.extract_plain_text().split(" ") if x.isdigit()])
    result: set = set(await plugin_data.config.get("ban", []))
    result.difference_update(lists)
    await plugin_data.config.set("ban", list(result))
    await unban.finish(f"已解封: {', '.join(lists)}")


@api_docs.handle()
async def handle_api_docs(bot: Bot, event: MessageEvent, args=CommandArg()):
    # /api_docs [api_key]
    args = args.extract_plain_text().strip()
    if not args:
        await handle_api_docs(
            bot, event, MessageChain([{"type": "Plain", "text": "1"}])
        )
        return
    elif args.isdigit():
        page = int(args)
        if page < 1:
            page = 1
        x = sorted(API_HANDLE.available_recipients.items(), key=lambda item: item[0])
        x = x[(page - 1) * 10 : page * 10]
        x = [f"- {k}: {v}" for k, v in x]
        await api_docs.finish(
            f"""[API DOCS] 用法: /api [api_key]
特别的，你可以使用 /api clear 来清除你的api_key
api_key:
"""
            + "\n".join(x)
        )
    elif args == "clear":
        user_api_manager.clear_user_apis(event.get_user_id())
        await api_docs.finish("已清除")
    else:
        try:
            ins = API_HANDLE[args](event.get_user_id())
            user_api_manager.activate_api(event.get_user_id(), args, ins)
            await api_docs.send(
                f"成功激活api_key: {args}\n目前一共激活了："
                + ";".join(
                    [i for i in user_api_manager.get_active_apis(event.get_user_id())]
                )
            )
        except Exception as e:
            await api_docs.finish(f"错误: {e}")


@set_.handle()
async def handle_set(bot: Bot, event: MessageEvent, args=CommandArg()):
    lists = [str(x.data["target"]) for x in args if x.type == MessageType.AT]
    args = args.extract_plain_text()
    args = args.split(" ")
    if len(args) < 2:
        await set_.finish("参数错误")
    if args[0] == "query_summary":
        await plugin_data.config.set("query_summary", int(args[1]))
        await set_.finish("设置成功")
    if args[0] == "cid":
        if len(args) <= 2:
            await set_.finish("参数错误")
        cid = None
        if len(args) > 2:
            cid = args[2]
        if args[1] == "llm":
            GPTCORE.llm.cid = cid
        else:
            GPTCORE.user_bot_cid[args[1]] = cid
        await set_.finish("设置成功")
    if args[0] == "limit":
        if len(args) < 2:
            await set_.finish("参数错误")
        if not lists:
            lists = [args[1]]
        uid = bot.adapter.get_name().split(maxsplit=1)[0].lower() + ":" + lists[0]
        data = await plugin_data.config.get("request_limit", {})
        data[uid] = 0
        await plugin_data.config.set("request_limit", data)
        await set_.finish(f"已清理{lists[0]}的请求次数")


@was_call.handle()
@was_mention.handle()
async def handle_was_mention(bot: Bot, event: MessageEvent):
    return await handle_chatbot(bot, event, "")


@gpt4.handle()
async def handle_gpt4(bot: Bot, event: MessageEvent, args: MessageChain = CommandArg()):
    if id := args.extract_first(MessageType.AT):
        id = str(id.data["target"])
    else:
        id = args.extract_plain_text().strip() or event.get_user_id()

    if id:
        result = await create_chat_bot(id if id else event.get_user_id(), "gpt-4", nickname=(await bot.user_profile(target=(int(id))))["nickname"])  # type: ignore
        await gpt4.finish(result)


@chatbot.handle()
async def handle_chatbot(bot: Bot, event: MessageEvent, args=CommandArg()):
    if not plugin_config.chat:
        return
    if await BAN(bot=bot, event=event):
        await bot.send(event=event, message="你已被封禁", at_sender=True)
        return
    if GPTCORE.is_be_using and not await GPTOWNER(bot=bot, event=event):
        await chatbot.finish("GPT 正在使用中，请稍后再试")

    try:
        user_id = event.get_user_id()
    except Exception:
        await chatbot.finish("获取用户信息失败")

    if not args:
        args = event.message_chain

    data = await plugin_data.config.get("request_limit", {})
    last_time = data.get("last_time", "")
    if last_time != datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"):
        data = {
            "last_time": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%d"
            )
        }
        await plugin_data.config.set("request_limit", data)
    count = data.get(
        f"{bot.adapter.get_name().split(maxsplit=1)[0].lower()}:{user_id}", 0
    )
    if not await GPTOWNER(bot=bot, event=event):
        data[f"{bot.adapter.get_name().split(maxsplit=1)[0].lower()}:{user_id}"] = (
            count + 1
        )  # type: ignore
        await plugin_data.config.set("request_limit", data)
    if not await COUNT_LIMIT(bot=bot, event=event):
        await chatbot.finish("非常抱歉，您的请求次数已达上限。（每天0点重置）")

    try:
        result = await GPTCORE.chat_bot(bot, event, args)
        if len(result) > 1:
            nickname = (await bot.bot_profile())["nickname"]
            # 构造成转发消息的形式
            nodeList = [
                {
                    "senderId": event.self_id if not i["recipient"] else 10000,
                    "time": int(datetime.datetime.now().timestamp()),
                    "senderName": i["recipient"] or nickname,
                    "messageChain": i["message"].export(),
                }
                for i in result[:-1]
            ]
            try:
                await chatbot.send(
                    message=MessageChain(
                        MessageSegment(
                            type=MessageType.FORWARD,
                            nodeList=nodeList,
                            display={
                                "title": "GPT的调用记录",
                                "brief": "[调用记录]",
                                "source": "调用记录",
                                "preview": [
                                    f"{nodeList[0]['senderName']}: {result[0]['message'].extract_plain_text()}..."
                                ],
                                "summary": "点击查看调用记录",
                            },
                        )
                    ),
                )
            except Exception as ex:
                nodeList = [
                    {
                        "senderId": 10000,
                        "time": int(datetime.datetime.now().timestamp()),
                        "senderName": "Error Info",
                        "messageChain": MessageChain(str(ex)).export(),
                    },
                    {
                        "senderId": 10000,
                        "time": int(datetime.datetime.now().timestamp()),
                        "senderName": "Node List",
                        "messageChain": MessageChain(str(nodeList)).export(),
                    },
                ]
                await chatbot.send(
                    message=MessageChain(
                        MessageSegment(
                            type=MessageType.FORWARD,
                            nodeList=nodeList,
                            display={
                                "title": "GPT的错误信息",
                                "brief": "[错误信息]",
                                "source": "错误信息",
                                "preview": [f"{nodeList[0]['senderName']}: {ex}..."],
                                "summary": "点击查看错误信息",
                            },
                        )
                    ),
                )
        await bot.send(
            event=event,
            message=result[-1]["message"],
            at_sender=False,
            quote=event.source.id if event.source else None,
        )
    except TimeoutError:
        await chatbot.send("请求超时，请稍后再试")
    except httpx.HTTPError as ex:
        if isinstance(ex, httpx.HTTPStatusError):
            if ex.response.status_code == 429:
                await chatbot.send("请求过于频繁，请稍后再试")
            else:
                await chatbot.send(f"错误代码：{ex.response.status_code}\n错误信息：{ex}")
        else:
            await chatbot.send("未知错误，请稍后再试：\n{e}\n{eargs}".format(e=ex, eargs=ex.args))
            raise ex
    except CBTError as ex:
        await chatbot.send(f"错误代码：{ex.code}\n错误信息：{ex.message}")


@reset.handle()
async def handle_reset(
    bot: Bot, event: MessageEvent, args: MessageChain = CommandArg()
):
    if await SUPERUSER(bot=bot, event=event):
        if args.extract_plain_text() == "all":
            await reset.finish(await GPTCORE.reset_chat_bot(bot, "all", "all"))
        lists = [str(x.data["target"]) for x in args if x.type == MessageType.AT]
        lists.extend([x for x in args.extract_plain_text().split(" ") if x.isdigit()])
        if lists:
            for id in lists:
                result = await GPTCORE.reset_chat_bot(bot, id, (await bot.user_profile(target=int(id)))["nickname"])
                await reset.send(result)
            return

    try:
        nickname = event.sender.name if isinstance(event, GroupMessage) else event.sender.nickname  # type: ignore
        result = await GPTCORE.reset_chat_bot(bot, event.get_user_id(), nickname)
        await bot.send(
            event=event, message=result, quote=event.source.id if event.source else None
        )
    except Exception as e:
        if isinstance(e, TimeoutError):
            await reset.send("请求超时，请稍后再试")
        elif isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 429:
                await reset.send("请求过于频繁，请稍后再试")
            else:
                await reset.send(f"错误代码：{e.response.status_code}\n错误信息：{e}")
        else:
            await reset.send("未知错误，请稍后再试：\n{e}\n{eargs}".format(e=e, eargs=e.args))
            raise e


@clear_record.handle()
async def handle_clear_record(bot: Bot, event: MessageEvent, args=CommandArg()):
    args = args.extract_plain_text()
    if args == "all":
        async with create_session() as session:
            stms = delete(ConversationId)
            await session.execute(stms)
            await session.commit()
        await del_all_message_records()
        await clear_record.finish("已清空所有记录")

    if args == "this":
        if isinstance(event, GroupMessage):
            await clear_message_records(group_ids=[str(event.sender.group.id)])
            await clear_record.send(f"已清空群{event.sender.group.id}的记录")
        else:
            await clear_record.finish("请在群聊中使用")
    if args.isdigit():
        await clear_message_records(user_ids=[args], detail_types=["friend", "others"])
        await clear_record.finish(f"已清空用户{args}的记录")

    await del_message_records_to_limit(plugin_config.max_length)
    await plugin_data.config.set(
        "last_clear_time", datetime.datetime.utcnow().timestamp()
    )
    await clear_record.finish(f"已清空剩余 {plugin_config.max_length} 条记录")


@event_postprocessor
async def record_recv_msg_mirai2(bot: Bot, event: MessageEvent):
    record = MessageRecord(
        bot_type=bot.type,
        bot_id=bot.self_id,
        platform="qq",
        time=remove_timezone(
            event.source.time if event.source else datetime.datetime.now()
        ),
        type="s" if event.sender.id == bot.self_id else "r",
        detail_type="friend"
        if isinstance(event, FriendMessage)
        else "group"
        if isinstance(event, GroupMessage)
        else "others",
        message_id=str(event.source.id if event.source else 0),
        message=event.message_chain.export(),
        user_id=str(event.sender.id),
        group_id=str(event.sender.group.id)
        if isinstance(event, GroupMessage)
        else None,
        quote_id=str(event.quote.id) if event.quote else None,
    )  # type: ignore
    async with create_session() as session:
        session.add(record)
        await session.commit()


@Bot.on_called_api
async def record_send_msg_mirai2(
    bot: BaseBot,
    e: Optional[Exception],
    api: str,
    data: Dict[str, Any],
    result: Optional[Dict[str, Any]],
):
    if e or not result:
        return
    if api[:5] != "send_" or api[-8:] != "_message":
        return
    record = MessageRecord(
        bot_type=bot.type,
        bot_id=bot.self_id,
        platform="qq",
        time=remove_timezone(datetime.datetime.now()),
        type="s",
        detail_type="friend"
        if api == "send_friend_message"
        else "group"
        if api == "send_group_message"
        else "others",
        message_id=result["messageId"],
        message=data["message_chain"].export(),
        user_id=str(data["target"]) if "target" in data else bot.self_id,
        group_id=str(data["group"]) if "group" in data else None,
        quote_id=data["quote"] if "quote" in data else None,
    )
    async with create_session() as session:
        session.add(record)
        await session.commit()


@manage.handle()
async def handle_manager(cmd: tuple[str, str] = Command()):
    func, action = cmd
    if func == "chat":
        if action == "open":
            plugin_config.chat = True
        else:
            plugin_config.chat = False
        await manage.finish(
            f"[ChatGPT] {action.capitalize()}{'d' if action[-1] == 'e' else 'ed'}"
        )


from typing import Tuple
import traceback
from .summarize import SummarizeLog
from .copywriting import cw_gene

SUMMARIZER = SummarizeLog(GPTCORE.llm)
summarize_ = nonebot.plugin.on_command(
    "sum",
    rule=nonebot.rule.to_me(),
    aliases={"summarize"},
    priority=9,
    block=True,
    permission=SUPERUSER,
)


@summarize_.handle()
async def handle_summarize(bot: Bot, event: MessageEvent):
    await summarize_.send("正在处理，请稍后...")

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
        result = await SUMMARIZER.summarize_message(bot, records)
        await summarize_.send(result)
        return
    except Exception as e:
        if isinstance(e, TimeoutError):
            await summarize_.finish("请求超时，请稍后再试")
        elif isinstance(e, httpx.HTTPStatusError):
            print(traceback.format_exc())
            if e.response.status_code == 429:
                await summarize_.finish("请求过于频繁，请稍后再试")
            else:
                await summarize_.finish(f"错误代码：{e.response.status_code}\n错误信息：{e}")
        else:
            await summarize_.send("未知错误，请稍后再试：\n{e}\n{eargs}".format(e=e, eargs=e.args))
            raise e


cw = nonebot.plugin.on_command("cw", priority=4, block=True)
manage = nonebot.plugin.on_command(
    ("cw", "oepn"),
    rule=nonebot.rule.to_me(),
    aliases={("cw", "close")},
    permission=SUPERUSER,
    block=True,
    priority=2,
)
cw_p = nonebot.plugin.on_command(("cw", "p"), priority=3, block=True)


@cw.handle()
async def cw_handle(bot: Bot, event: MessageEvent, args: MessageChain = CommandArg()):
    await cw_gene(bot, event, args, cw)


@cw_p.handle()
async def cw_p_handle(bot: Bot, event: MessageEvent, args: MessageChain = CommandArg()):
    if not await SUPERUSER(bot=bot, event=event):
        await cw_p.finish("[文案] 请使用 /cw 命令，政治安全模式")
    await cw_gene(bot, event, args, cw, PoliticsSafe=False)


@manage.handle()
async def handle_first_receive(cmd: Tuple[str, str] = Command()):
    _, action = cmd
    if action == "open":
        plugin_config.cw = True
    else:
        plugin_config.cw = False
    await manage.finish(
        f"[文案] {action.capitalize()}{'d' if action[-1] == 'e' else 'ed'}"
    )
