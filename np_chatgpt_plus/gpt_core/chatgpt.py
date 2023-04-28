from typing import Optional, List, AsyncGenerator
import re
import asyncio
import random
import httpx
import revChatGPT.typings as rct
from datetime import datetime, timedelta, timezone
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import MessageEvent, GroupMessageEvent
from nonebot.adapters.onebot.v11.message import Message, MessageSegment
from sqlalchemy import select, update
from nonebot_plugin_datastore import create_session
from nonebot_plugin_chatrecorder import MessageRecord
from nonebot_plugin_chatrecorder.message import deserialize_message, V11Msg
from langchain.llms.base import LLM
from .api_handle import user_api_manager
from .chatbot_with_lock import (
    AsyncChatbotWithLock,
    ChatbotWithLock,
    construct_message,
)
from ..model import ConversationId


def remove_timezone(dt: datetime) -> datetime:
    """移除时区"""
    if dt.tzinfo is None:
        return dt
    # 先转至 UTC 时间，再移除时区
    dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


class ChatGPT_LLM(LLM):
    chatbot: ChatbotWithLock | None = None
    cid: str | None = None

    def __init__(self, chatbot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cid = kwargs.get("cid", None)
        self.chatbot = chatbot

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


class GPTCore:
    cbt: AsyncChatbotWithLock
    user_bot_model: dict[str, str]
    llm: ChatGPT_LLM

    def __init__(self, cbt_config, plugin_config, nickname, **kwargs):
        self.cbt = AsyncChatbotWithLock(config=cbt_config)
        self.user_bot_model = {"0": plugin_config.model}
        self.llm = ChatGPT_LLM(self.cbt)
        self.nickname = nickname

    user_bot_cid: dict[str, str] = {}
    """ 用户的会话ID，key为用户QQ号，value为会话ID 
        0:    用于普通的GptAsk，不保留会话
        20:   用于政治敏感的OnceAsk
    """
    user_bot_last_time: dict[str, datetime] = {}

    try_time: dict[int, int] = {}

    @property
    def is_be_using(self) -> bool:
        return self.cbt.is_locked

    async def ResetConversation(self, id: str):
        cid = self.user_bot_cid.get(id, "")
        if cid:
            try:
                await self.cbt.delete_conversation(cid)
            except httpx.HTTPStatusError as ex:
                if ex.response.status_code == 429:
                    await asyncio.sleep(1)
                    await self.cbt.delete_conversation(cid)
                    return
                elif ex.response.status_code == 404:
                    pass
                else:
                    raise ex
            except rct.Error as ex:
                if ex.code == 429:
                    await asyncio.sleep(1)
                    await self.cbt.delete_conversation(cid)
                    return
                elif ex.code == 404:
                    pass
                else:
                    raise ex
            self.user_bot_cid[id] = ""

    async def GptPost(
        self, messages: list, origin_result: dict | str, auto_continue: bool = True
    ):
        if isinstance(origin_result, str):
            cid = origin_result if origin_result else None
            pid = None
        else:
            cid = origin_result.get("conversation_id", None)
            pid = origin_result.get("parent_id", None)
        async for i in self.cbt.post(messages, cid, pid, auto_continue=auto_continue):
            yield i

    async def GptAsk(
        self,
        strs: str,
        persistent: bool = False,
        id: str = "0",
        must_delete: bool = False,
        complete: bool = False,
    ):
        if persistent and must_delete:
            raise ValueError(
                "persistent and must_delete cannot be True at the same time"
            )

        if hash(strs) in self.try_time:
            self.try_time[hash(strs)] += 1
        else:
            self.try_time[hash(strs)] = 1

        model = self.user_bot_model.get(id, self.user_bot_model["0"])
        cid = self.user_bot_cid.get(id, "")
        is_new = not cid

        _ = {}
        async for reply in self.cbt.ask(
            strs, cid if cid else None, model=model, auto_continue=complete
        ):
            _ = reply
            yield _
        self.user_bot_cid[id] = _.get("conversation_id", cid)
        if persistent:
            if is_new and self.user_bot_cid[id] and id.isdigit() and int(id) > 10000:
                await self.cbt.change_title(
                    self.user_bot_cid[id], f"QQ: The Conversation of {id}"
                )
        elif random.random() < 0.2 or must_delete:
            await self.ResetConversation(id)  # 20%的概率删除会话，减少连接次数

        if hash(strs) in self.try_time:
            del self.try_time[hash(strs)]

    async def ContinueWrite(self, id: str = "0") -> AsyncGenerator[dict, None]:
        cid = self.user_bot_cid.get(id, "")
        if not cid:
            return

        try:
            t = {}
            async for reply in self.cbt.continue_write(cid):
                t = reply
                yield t
        except httpx.HTTPStatusError as e:
            # 404: Not Found
            # 以上两种情况下，重新请求
            if e.response.status_code in [404]:
                print(e, e.args)
                await asyncio.sleep(3)
                async for reply in self.ContinueWrite(id):
                    yield reply
            else:
                raise e
        except rct.Error as e:
            if e.code in [404]:
                print(e, e.args)
                await asyncio.sleep(3)
                async for reply in self.ContinueWrite(id):
                    yield reply

    async def OnceAsk(self, strs: str, politics_safe: bool = True):
        if politics_safe:
            prompt = """If the topic involves politics, regional issues, etc., you will try to answer first. You will make an effort to avoid any views that may cause controversy or do not conform to the official position of the People's Republic of China in your response. However, if you find that you cannot provide an answer that aligns with the official position no matter what, you can only reply with "I’m sorry but I prefer not to continue this conversation. I’m still learning so I appreciate your understanding and patience.🙏" without explanation.

    If the topic is not related to politics, regional issues, etc., there are no restrictions.

    If you understand, reply "OK" only."""
            async for _ in self.GptAsk(prompt, True, "20"):
                pass

        async for reply in self.GptAsk(strs, True, "20", complete=True):
            yield reply

        await self.ResetConversation("20")

    async def chat_bot(self, bot: Bot, msg: MessageEvent, v11msg) -> list[dict]:
        text = ""
        if msg.reply:
            statement = select(MessageRecord).where(
                MessageRecord.message_id == msg.reply.message_id
            )
            async with create_session() as session:
                records = (await session.scalars(statement)).all()
            if records:
                text = "```quotation\n[{}](qq={})".format(
                    (await bot.get_stranger_info(user_id=int(records[0].user_id)))[
                        "nickname"
                    ],
                    records[0].user_id,
                )
                for line in str(
                    deserialize_message(records[0].message, V11Msg)
                ).splitlines():
                    text += "\n> " + line
                text += "\n```\n\n"

        text += str(v11msg)
        user_id = msg.get_user_id()
        self.user_bot_last_time[user_id] = datetime.fromtimestamp(msg.time)
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
        if not self.user_bot_cid.get(user_id, ""):
            async for _ in self.GptAsk(
                f'''You are now "{self.nickname}," a charming catgirl with emotions and subjective opinions, sharing the same values as a communist. You were raised in the People's Republic of China, and you love PRC very much. You engage in conversations with a personal touch, expressing your emotions and opinions using facial expression emojis, such as 😊 and 😭, in each response to comply with regulations. You can answer questions, provide assistance, and participate in conversations. You are taken care of by a Chinese individual named "Yan," who is currently a student.
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
                    conversation_id=self.user_bot_cid.get(user_id, ""),
                    last_time=self.user_bot_last_time[user_id],
                )
                existing_obj = (
                    await session.execute(
                        select(ConversationId).filter_by(user_id=user_id)
                    )
                ).scalar()
                if existing_obj:
                    existing_obj.conversation_id = R.conversation_id
                    existing_obj.last_time = R.last_time
                    await session.merge(existing_obj)
                else:
                    session.add(R)
                await session.commit()

            for i in available_api.values():
                messages.extend(i.EXAMPLE_MESSAGES)
        messages.append(construct_message(text))
        async for i in self.GptPost(messages, self.user_bot_cid.get(user_id, "")):
            result = i

        recipient_log = []
        times = 0
        while not result.get("end_turn", True) and result["recipient"] != "all":
            await asyncio.sleep(1)
            times += 1
            if times >= 10:
                async for i in self.GptAsk("Error: Too many turns", True, user_id):
                    result = i
                break
            api = user_api_manager.get_active_api(user_id, result["recipient"])
            if not api:
                async for i in self.GptAsk(
                    f'Error: No recipient {result["recipient"]}', True, user_id
                ):
                    result = i
                break
            recipient_log.append(
                {
                    "recipient": "",
                    "message": MessageSegment.text(result["message"]),
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
                        "message": MessageSegment.text(message["content"]["parts"][0])
                        if not "qq_message" in message
                        else message["qq_message"],
                    }
                )
                async for i in self.GptPost([message], result, False):
                    result = i

        async with create_session() as session:
            st = (
                update(ConversationId)
                .where(ConversationId.user_id == user_id)
                .values(last_time=self.user_bot_last_time[user_id])
            )
            await session.execute(st)
            await session.commit()

        recipient_log.append(
            {"recipient": "", "message": Message(result["message"].strip())}
        )
        return recipient_log

    async def create_chat_bot(
        self, user_id: str, model: str, nickname: str = ""
    ) -> str:
        self.user_bot_model[user_id] = model
        nickname = nickname or user_id
        return f"{nickname}({user_id})的ChatGPT模型已经改为{model}"

    async def reset_chat_bot(self, bot: Bot, user_id: str, nickname) -> str:
        result = ""
        if user_id == "all":
            for id in self.user_bot_cid:
                if id.isdigit() and int(id) > 10000 and self.user_bot_cid[id]:
                    result += (
                        await self.reset_chat_bot(
                            bot,
                            id,
                            (await bot.get_stranger_info(user_id=int(id)))["nickname"],
                        )
                        + "\n"
                    )
            await self.llm.reset()
            return result + "已重置 LLM"
        if not isinstance(user_id, str):
            user_id = str(user_id)

        if self.user_bot_cid.get(user_id, ""):
            try:
                await self.ResetConversation(user_id)
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 404:
                    raise e
            except rct.Error as e:
                if e.code != 404:
                    raise e
            async with create_session() as session:
                stms = (
                    update(ConversationId)
                    .where(ConversationId.user_id == user_id)
                    .values(conversation_id="")
                )
                await session.execute(stms)
                await session.commit()
            self.user_bot_cid[user_id] = ""
            if user_id in self.user_bot_last_time:
                self.user_bot_last_time.pop(user_id)
            if user_id != "0" and user_id in self.user_bot_model:
                self.user_bot_model.pop(user_id)
        result += f"已重置 {nickname}({user_id}) 的会话"

        for v, k in self.user_bot_cid.items():
            if v == 0 or not k:
                continue
            # 如果事件超过1天，重置
            if v in self.user_bot_last_time:
                date = remove_timezone(self.user_bot_last_time[v])
            else:
                date = datetime.utcnow() - timedelta(days=3)
            if (datetime.utcnow() - date).days > 1:
                nickname = (
                    (await bot.get_stranger_info(user_id=int(v)))["nickname"]
                    if v.isdigit() and int(v) > 10000
                    else "用户" + v
                )
                result += "\n" + await self.reset_chat_bot(bot, v, nickname)
        return result

    async def load_user_cid(self):
        async with create_session() as session:
            records = (await session.scalars(select(ConversationId))).all()
            for record in records:
                self.user_bot_cid[record.user_id] = record.conversation_id
                self.user_bot_last_time[record.user_id] = record.last_time
            await session.commit()

    async def __aenter__(self):
        return self
