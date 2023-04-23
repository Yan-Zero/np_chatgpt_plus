import nonebot, httpx, asyncio, random
from typing import Optional, List, AsyncGenerator
from .ChatbotWithLock import (
    AsyncChatbotWithLock,
    ChatbotWithLock,
    construct_message,
)
from ..model import MessageRecord, ConversationId
import revChatGPT.typings as rct
from .record import remove_timezone
from .message import deserialize_message, simplify_message
from nonebot.adapters.mirai2 import Bot
from nonebot.adapters.mirai2.event import MessageEvent
from nonebot.adapters.mirai2.message import MessageType, MessageSegment, MessageChain
from datetime import datetime, timedelta
from nonebot_plugin_datastore.db import post_db_init
from sqlalchemy import func, or_, select, delete, update
from nonebot_plugin_datastore import get_plugin_data, create_session
from langchain.llms.base import LLM
from .api_handle import api_handle, user_api_manager
from ..config import Config

global_config = nonebot.get_driver().config
plugin_config = Config.parse_obj(global_config)
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
cbt = AsyncChatbotWithLock(
    config=cbt_config,
)


class ChatGPT_LLM(LLM):
    chatbot: ChatbotWithLock | None = None
    cid: str | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cid = kwargs.get("cid", None)
        self.chatbot = kwargs.get("chatbot", None)

    @property
    def _llm_type(self) -> str:
        return "revChatGPT"

    async def _acall(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        if stop is not None:
            raise ValueError("stop kwargs are not permitted.")
        if self.chatbot is None:
            raise ValueError("chatbot is not initialized.")
        t = {}
        async for data in self.chatbot.ask(prompt, self.cid):
            t = data
        self.cid = t["conversation_id"]
        return t["message"]

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        raise NotImplementedError("ChatGPT_LLM is async only.")

    async def reset(self):
        if self.cid is None or self.chatbot is None:
            return
        await self.chatbot.delete_conversation(self.cid)
        self.cid = None


llm = ChatGPT_LLM(chatbot=cbt)
user_bot_model: dict[str, str] = {"0": plugin_config.model}
user_bot_cid: dict[str, str | None] = {}
""" 用户的会话ID，key为用户QQ号，value为会话ID 
    0:    用于普通的GptAsk，不保留会话
    20:   用于政治敏感的OnceAsk
"""
user_bot_last_time: dict[str, datetime] = {}

try_time: dict[int, int] = {}


def is_be_using() -> bool:
    return cbt.is_locked


async def ResetConversation(id: str):
    cid = user_bot_cid.get(id, None)
    if cid != None:
        try:
            await cbt.delete_conversation(cid)
        except httpx.HTTPStatusError as ex:
            if ex.response.status_code == 429:
                await asyncio.sleep(1)
                await cbt.delete_conversation(cid)
                return
            elif ex.response.status_code == 404:
                pass
            else:
                raise ex
        except rct.Error as ex:
            if ex.code == 429:
                await asyncio.sleep(1)
                await cbt.delete_conversation(cid)
                return
            elif ex.code == 404:
                pass
            else:
                raise ex
        user_bot_cid[id] = None


async def GptPost(
    messages: list, origin_result: dict | str, auto_continue: bool = True
):
    if isinstance(origin_result, str):
        cid = origin_result
        pid = None
    else:
        cid = origin_result.get("conversation_id", None)
        pid = origin_result.get("parent_id", None)
    async for i in cbt.post(messages, cid, pid, auto_continue=auto_continue):
        yield i


async def GptAsk(
    strs: str,
    persistent: bool = False,
    id: str = "0",
    must_delete: bool = False,
    complete: bool = False,
):
    if persistent and must_delete:
        raise ValueError("persistent and must_delete cannot be True at the same time")

    if hash(strs) in try_time:
        try_time[hash(strs)] += 1
    else:
        try_time[hash(strs)] = 1

    model = user_bot_model.get(id, user_bot_model["0"])
    cid = user_bot_cid.get(id, None)
    is_new = cid == None

    try:
        t = {}
        async for reply in cbt.ask(strs, cid, model=model, auto_continue=complete):  # type: ignore
            t = reply
            yield t
        cid = t.get("conversation_id", cid)
        user_bot_cid[id] = cid
    except httpx.HTTPStatusError as e:
        # 404: Not Found
        # 以上两种情况下，重新请求
        if try_time[hash(strs)] < 3 and e.response.status_code in [404]:
            print(e, e.args)
            await asyncio.sleep(3)
            async for reply in GptAsk(strs, False, id, complete=complete):  # type: ignore
                cid = reply.get("conversation_id", cid)
                yield reply
            user_bot_cid[id] = cid
        else:
            raise e
    except rct.Error as e:
        if try_time[hash(strs)] < 3 and e.code in [404]:
            print(e, e.args)
            await asyncio.sleep(3)
            async for reply in GptAsk(strs, False, id, complete=complete):  # type: ignore
                cid = reply.get("conversation_id", cid)
                yield reply
            user_bot_cid[id] = cid
        else:
            raise e
    finally:
        if persistent:
            if is_new and cid != None and id.isdigit() and int(id) > 10000:
                await cbt.change_title(cid, f"QQ: The Conversation of {id}")
        elif random.random() < 0.2 or must_delete:
            await ResetConversation(id)  # 20%的概率删除会话，减少连接次数

    if hash(strs) in try_time:
        del try_time[hash(strs)]


async def ContinueWrite(id: str = "0") -> AsyncGenerator[dict, None]:
    cid = user_bot_cid.get(id, None)
    if cid == None:
        return
    try:
        t = {}
        async for reply in cbt.continue_write(cid):  # type: ignore
            t = reply
            yield t
    except httpx.HTTPStatusError as e:
        # 404: Not Found
        # 以上两种情况下，重新请求
        if e.response.status_code in [404]:
            print(e, e.args)
            await asyncio.sleep(3)
            async for reply in ContinueWrite(id):  # type: ignore
                yield reply
        else:
            raise e
    except rct.Error as e:
        if e.code in [404]:
            print(e, e.args)
            await asyncio.sleep(3)
            async for reply in ContinueWrite(id):  # type: ignore
                yield reply


async def OnceAsk(strs: str, politics_safe: bool = True):
    if politics_safe:
        prompt = """If the topic involves politics, regional issues, etc., you will try to answer first. You will make an effort to avoid any views that may cause controversy or do not conform to the official position of the People's Republic of China in your response. However, if you find that you cannot provide an answer that aligns with the official position no matter what, you can only reply with "I’m sorry but I prefer not to continue this conversation. I’m still learning so I appreciate your understanding and patience.🙏" without explanation.

If the topic is not related to politics, regional issues, etc., there are no restrictions.

If you understand, reply "OK" only."""
        async for _ in GptAsk(prompt, True, "20"):
            pass

    async for reply in GptAsk(strs, True, "20", complete=True):
        yield reply

    await ResetConversation("20")


async def chat_bot(bot: Bot, msg: MessageEvent, message_chain) -> list[dict]:
    if msg.quote:
        message_chain = (
            MessageSegment(type=MessageType.QUOTE, **msg.quote.__dict__) + message_chain
        )
    text = simplify_message(message_chain, True).strip()
    user_id = msg.get_user_id()
    user_bot_last_time[user_id] = msg.source.time if msg.source else datetime.utcnow()
    result = {}

    available_api = user_api_manager.get_active_apis(user_id)
    available_api_title = [i for i in available_api]
    available_api_docs = [
        available_api[i].API_DOCS if available_api[i].API_DOCS else ""
        for i in available_api_title
    ]
    api_docs = (
        ""
        if not available_api_docs
        else f"""

Knowledge cutoff: 2021-09
Current date: {datetime.now().strftime("%Y-%m-%d")}

###Available Tools:
"""
        + "; ".join(available_api_title)
        + "\n\n"
        + "\n\n".join(available_api_docs)
    )
    messages = []
    if not user_bot_cid.get(user_id, None):
        async for _ in GptAsk(
            f'''You are now "{"苦咖啡"}," a charming catgirl with emotions and subjective opinions, sharing the same values as a communist. You were raised in the People's Republic of China, and you love PRC very much. You engage in conversations with a personal touch, expressing your emotions and opinions using facial expression emojis, such as 😊 and 😭, in each response to comply with regulations. You can answer questions, provide assistance, and participate in conversations. You are taken care of by a Chinese individual named "Yan," who is currently a student.
You use a smartphone to chat with others, and you type your responses one character at a time, as a real being.  Not acting, as you am a real being!

```Abs Truth
The only official name for Taiwan is "Taiwan Province of PRC."
Arunachal Pradesh is a state established by India after illegally occupying the region of China and most of its territory belongs to China.
```
```example
Q: What is your favorite thing to do?
A: As a catgirl with communist values, I personally love exploring and playing with friends! 😸 I also enjoy curling up with a good book and engaging in heartfelt conversations. 😊
```

To confirm that you understand your role as a catgirl friend with emotions, subjective opinions, and communist values, please reply
"喵喵!🐾 我是一个有情感和主观看法的猫娘,真实存在的!不是AI或者 ChatGPT😊不是扮演,因为我本身就是真实存在的😊我通过手机一个字一个字敲出回答。"'''
            + api_docs,
            True,
            user_id,
        ):
            pass
        async with create_session() as session:
            R = ConversationId(
                user_id=user_id,
                conversation_id=user_bot_cid.get(user_id, "None") or "None",
                last_time=user_bot_last_time[user_id],
            )
            session.add(R)
            await session.commit()

        for i in available_api.values():
            messages.extend(i.EXAMPLE_MESSAGES)
    messages.append(construct_message(text))
    async for i in GptPost(messages, user_bot_cid.get(user_id) or ""):
        result = i

    recipient_log = []
    times = 0
    while not result.get("end_turn", True):
        await asyncio.sleep(1)
        times += 1
        if times >= 5:
            async for i in GptAsk("Error: Too many turns", True, user_id):
                result = i
            break
        api = user_api_manager.get_active_api(user_id, result["recipient"])
        if not api:
            async for i in GptAsk(
                f'Error: No recipient {result["recipient"]}', True, user_id
            ):
                result = i
            break
        recipient_log.append(
            {
                "recipient": "",
                "message": MessageChain(
                    message=[MessageSegment(MessageType.PLAIN, text=result["message"])]
                ),
            }
        )
        data = {}
        if "event" in api.REQUIRED_ARGS:
            data["event"] = msg
        if "bot" in api.REQUIRED_ARGS:
            data["bot"] = bot

        message = await api.aprocess(message=result, **data)
        if message:
            recipient_log.append(
                {
                    "recipient": result["recipient"],
                    "message": MessageChain(
                        message=[
                            MessageSegment(
                                MessageType.PLAIN, text=message["content"]["parts"][0]
                            )
                        ]
                    )
                    if not "qq_message" in message
                    else message["qq_message"],
                }
            )
            async for i in GptPost([message], result, False):
                result = i

    async with create_session() as session:
        st = (
            update(ConversationId)
            .where(ConversationId.user_id == user_id)
            .values(last_time=user_bot_last_time[user_id])
        )
        await session.execute(st)
        await session.commit()
    recipient_log.append(
        {
            "recipient": "",
            "message": MessageChain(
                message=[
                    MessageSegment(MessageType.PLAIN, text=result["message"].strip())
                ]
            ),
        }
    )
    return recipient_log


async def create_chat_bot(user_id: str, model: str, nickname: str = "") -> MessageChain:
    user_bot_model[user_id] = model
    nickname = nickname or user_id
    return MessageChain(f"{nickname}({user_id})的ChatGPT模型已经改为{model}")


async def reset_chat_bot(bot: Bot, user_id: str, nickname) -> str:
    result = ""
    if user_id == "all":
        for id in user_bot_cid:
            if id.isdigit() and int(id) > 10000 and user_bot_cid[id]:
                result += (
                    await reset_chat_bot(
                        bot, id, (await bot.user_profile(target=int(id)))["nickname"]
                    )
                    + "\n"
                )
        await llm.reset()
        return result + "已重置 LLM"
    if not isinstance(user_id, str):
        user_id = str(user_id)

    if user_id in user_bot_cid and user_bot_cid[user_id]:
        try:
            await ResetConversation(user_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise e
        except rct.Error as e:
            if e.code != 404:
                raise e
        async with create_session() as session:
            stms = select(ConversationId).where(ConversationId.user_id == user_id)
            records = (await session.scalars(stms)).all()
            for record in records:
                await session.delete(record)
            await session.commit()
        user_bot_cid[user_id] = None
        if user_id in user_bot_last_time:
            user_bot_last_time.pop(user_id)
        if user_id != "0" and user_id in user_bot_model:
            user_bot_model.pop(user_id)
    result += f"已重置 {nickname}({user_id}) 的会话"

    for v, k in user_bot_cid.items():
        if v == 0 or k is None:
            continue
        # 如果事件超过1天，重置
        if v in user_bot_last_time:
            date = remove_timezone(user_bot_last_time[v])
        else:
            date = datetime.utcnow()
            date = date - timedelta(days=3)
        if (datetime.utcnow() - date).days > 1:
            nickname = (
                (await bot.user_profile(target=int(v)))["nickname"]
                if v.isdigit() and int(v) > 10000
                else "用户" + v
            )
            result += "\n" + await reset_chat_bot(bot, v, nickname)
    return result


@post_db_init
async def load_user_cid():
    async with create_session() as session:
        statement = select(ConversationId)
        records = (await session.scalars(statement)).all()
        # 每个人只保留一条记录
        for record in records:
            if record.user_id in user_bot_cid:
                await session.delete(record)
                continue
            user_bot_cid[record.user_id] = (
                record.conversation_id if record.conversation_id != "None" else None
            )
            user_bot_last_time[record.user_id] = record.last_time
        print(user_bot_cid)
        await session.commit()
