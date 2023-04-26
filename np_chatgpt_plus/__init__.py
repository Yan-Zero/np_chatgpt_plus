"""

"""
import datetime
import httpx
import nonebot

nonebot.require("nonebot_plugin_datastore")
nonebot.require("nonebot_plugin_chatrecorder")
from revChatGPT.typings import Error as CBTError
import nonebot.plugin, nonebot.rule
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import (
    MessageEvent,
    GroupMessageEvent,
    PrivateMessageEvent,
)
from nonebot.adapters.onebot.v11.permission import GROUP, PRIVATE
from nonebot.adapters import Bot as BaseBot
from nonebot.adapters.onebot.v11.message import Message as V11Msg
from nonebot.adapters.onebot.v11.message import MessageSegment
from nonebot.params import CommandArg, Command
from nonebot_plugin_datastore import get_plugin_data, create_session
from nonebot.message import event_postprocessor
from typing import Optional, Dict, Any
from nonebot_plugin_datastore.db import post_db_init
from nonebot_plugin_chatrecorder import get_message_records
from nonebot.adapters.onebot.v11.bot import send
from .rule import BAN, COUNT_LIMIT, GPTOWNER, SUPERUSER
from .gpt_core import GPTCore
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
async def handle_ban(args: V11Msg = CommandArg()):
    if not args:
        await rule_.finish("参数错误")
    lists = [x.data["user_id"] for x in args if x.type == "mention"]
    lists.extend([x for x in args.extract_plain_text().split(" ") if x.isdigit()])
    lists = set(lists)
    lists.update(await plugin_data.config.get("ban", set()))
    await plugin_data.config.set("ban", list(lists))
    await rule_.finish(f"已封禁: {', '.join(lists)}")


@unban.handle()
async def handle_unban(args: V11Msg = CommandArg()):
    if not args:
        await unban.finish("参数错误")
    lists = [x.data["user_id"] for x in args if x.type == "mention"]
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
        await handle_api_docs(bot, event, V11Msg("1"))
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
    lists = [x.data["user_id"] for x in args if x.type == "mention"]
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
async def handle_gpt4(bot: Bot, event: MessageEvent, args: V11Msg = CommandArg()):
    if id := args.get("mention", 1):
        id = id[0].data["user_id"]
    else:
        id = args.extract_plain_text().strip() or event.get_user_id()
    id = id or event.get_user_id()
    if id:
        result = await GPTCORE.create_chat_bot(
            id,
            "gpt-4",
            nickname=(await bot.get_stranger_info(user_id=int(id)))["user_name"],
        )
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
        args = event.message

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
            nickname = bot.config.nickname
            # 构造成转发消息的形式
            nodeList = [
                {
                    "type": "node",
                    "data": {
                        "name": i["recipient"] or nickname,
                        "uin": bot.self_id if not i["recipient"] else "10000",
                        "content": repr(i["message"]),
                    },
                }
                for i in result[:-1]
            ]

            try:
                # await chatbot.send(
                #     message=V11Msg(
                #         MessageSegment(
                #             type=MessageType.FORWARD,
                #             nodeList=nodeList,
                #             display={
                #                 "title": "GPT的调用记录",
                #                 "brief": "[调用记录]",
                #                 "source": "调用记录",
                #                 "preview": [
                #                     f"{nodeList[0]['senderName']}: {result[0]['message'].extract_plain_text()}..."
                #                 ],
                #                 "summary": "点击查看调用记录",
                #             },
                #         )
                #     ),
                # )
                chatbot.send(message=V11Msg())
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
        await send(
            bot=bot,
            event=event,
            message=result[-1]["message"],
            at_sender=False,
            reply_message=True,
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
async def handle_reset(bot: Bot, event: MessageEvent, args: V11Msg = CommandArg()):
    if await SUPERUSER(bot=bot, event=event):
        if args.extract_plain_text() == "all":
            await reset.finish(await GPTCORE.reset_chat_bot(bot, "all", "all"))
        lists = [x.data["user_id"] for x in args if x.type == "mention"]
        lists.extend([x for x in args.extract_plain_text().split(" ") if x.isdigit()])
        if lists:
            for id in lists:
                result = await GPTCORE.reset_chat_bot(
                    bot, id, (await bot.get_stranger_info(user_id=int(id)))["user_name"]
                )
                await reset.send(result)
            return

    try:
        result = await GPTCORE.reset_chat_bot(
            bot,
            event.get_user_id(),
            (await bot.get_user_info(user_id=event.get_user_id()))["user_name"],
        )
        await send(bot=bot, event=event, message=result, reply_message=True)
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


import traceback
from .summarize import SummarizeLog

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

    if isinstance(event, GroupMessageEvent):
        records = await get_message_records(
            group_ids=[event.group_id],
            time_start=datetime.datetime.utcnow() - datetime.timedelta(days=1),
        )
    elif isinstance(event, PrivateMessageEvent):
        records = await get_message_records(
            user_ids=[event.get_user_id()],
            detail_types=["private"],
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


from .copywriting import cw
