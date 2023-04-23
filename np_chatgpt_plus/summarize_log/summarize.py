from typing import Sequence
from langchain.chains.summarize import load_summarize_chain
from ..gpt_core.model import MessageRecord, ConversationId
from ..gpt_core.record import remove_timezone
from ..gpt_core.message import deserialize_message, simplify_message
from ..gpt_core.chatgpt import GptAsk, llm
from ..gpt_core.ChatbotWithLock import get_code_from_markdown, get_token_count
import nonebot, httpx, asyncio, random, traceback
from langchain.docstore.document import Document
from nonebot.adapters.mirai2 import Bot
from nonebot.adapters.mirai2.event import MessageEvent
from nonebot.adapters.mirai2.message import MessageType, MessageSegment, MessageChain
from datetime import datetime, timedelta
from nonebot_plugin_datastore.db import post_db_init
from sqlalchemy import func, or_, select, delete, update
from nonebot_plugin_datastore import get_plugin_data, create_session
from langchain.prompts import PromptTemplate


PROMPT_INIT = PromptTemplate(
    template="""````template
整体感情: ...
最近的消息主要聊了如下主题:
1. 
2. 
...(最多5条)(高度概况性的)

用词最不友善ID的是: ...!
````

Using the template below to write a concise summary of the following conversation:
````Conversation log
{text}
````

CONCISE SUMMARY:""",
    input_variables=["text"],
)
PROMPT_COMB = PromptTemplate(
    template=(
        "Your job is to produce a final summary\n"
        "We have provided an existing summary up to a certain point:\n"
        "------------\n"
        "{existing_answer}\n"
        "------------\n"
        "We have the opportunity to fine-tuning the existing summary"
        "(only if needed) with some more conversation log below.\n"
        "------------\n"
        "{text}\n"
        "------------\n"
        "Given the new conversation log, fine-tuning the original summary(such as merge some topic)\n"
        "Each topic is as short as possible.\n"
        "Please use the following template:\n"
        "````template\n"
        "整体感情: ...\n"
        "最近的消息主要聊了如下主题:\n"
        "1. \n"
        "2. \n"
        "...(最多5条)\n"
        "\n"
        "用词最不友善ID的是: ...!\n"
        "````"
    ),
    input_variables=["existing_answer", "text"],
)
chain = load_summarize_chain(
    llm,
    chain_type="refine",
    verbose=False,
    refine_prompt=PROMPT_COMB,
    question_prompt=PROMPT_INIT,
)


async def mapping_user(bot: Bot, user_mapping: dict, text: str) -> str:
    """将用户ID映射到用户昵称

    Args:
        bot (Bot): Bot
        user_mapping (dict): 用户ID映射表
        text (str): 文本

    Returns:
        str: 映射后的文本
    """
    for user_id, user_name in user_mapping.items():
        user_name = "ID " + str(user_name)
        text = text.replace(
            user_name,
            f"{(await bot.user_profile(target=int(user_id)))['nickname']}({user_id})",
        )

    return text


async def summarize_message(bot: Bot, msgs: Sequence[MessageRecord]) -> str:
    """生成一段对话的总结

    Args:
        bot (Bot): Bot
        msgs (Sequence[MessageRecord]): 对话记录
        user_id_map (dict | None, optional): 用户ID映射表. Defaults to None.
        part (int | None, optional): 用于分段总结. Defaults to None.

    Returns:
        str: 总结
    """

    user_id_map = {msgs[0].bot_id: 0}
    for msg in msgs:
        if msg.user_id not in user_id_map:
            user_id_map[msg.user_id] = len(user_id_map)

    conversation_log = []
    t = ""
    for msg in msgs:
        message = simplify_message(deserialize_message(msg.message))
        if (
            msg.type == "s"
            and "用词最不友善ID的是" in message
            and "感情" in message
            and "主题" in message
        ):
            continue
        j = user_id_map[msg.user_id if msg.type == "r" else msg.bot_id]
        t += f"ID:{j},MsgID:{msg.message_id}\n{message}\n\n"
        if get_token_count(t) > 2000:
            conversation_log.append(t.strip())
            t = ""
    if t.strip():
        conversation_log.append(t.strip())

    content = await chain.arun(
        input_documents=[Document(page_content=c) for c in conversation_log]
    )

    #     ask = """Please summarize the conversation following the template. {part_count}

    # ````template
    # 整体感情: ...
    # 最近的消息主要聊了如下主题:
    # 1.
    # 2.
    # ...(最多5条)

    # 用词最不友善ID的是: ...!
    # ````

    # ````Conversation log
    # {conversation_log}
    # ````"""
    #     part_count = ""
    #     count = 0
    #     result = {}
    #     while len(conversation_log) > 2:
    #         count += 1
    #         part_count = f"This is part {count} of {len(conversation_log)}. Remember to combine records from other parts."
    #         msg = conversation_log.pop(0)
    #         async for i in GptAsk(
    #             ask.format(part_count=part_count, conversation_log=msg),
    #             persistent=True,
    #             id="summarize_log",
    #         ):
    #             result = i
    #         print(result["message"])
    #     if part_count:
    #         part_count = f"This is last part of {len(conversation_log)}. Remember to combine records from other parts."
    #     msg = conversation_log.pop(0)
    #     async for i in GptAsk(
    #         ask.format(part_count=part_count, conversation_log=msg),
    #         persistent=False,
    #         id="summarize_log",
    #         must_delete=True,
    #     ):
    #         result = i

    await llm.reset()
    return (
        f"一共处理了{len(msgs)}条消息\n\n" + await mapping_user(bot, user_id_map, content)
    ).strip()
