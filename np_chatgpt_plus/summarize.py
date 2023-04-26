from typing import Sequence
from nonebot_plugin_chatrecorder import MessageRecord
from nonebot_plugin_chatrecorder.message import deserialize_message, V11Msg
from nonebot.adapters.onebot.v11 import Bot
from langchain.prompts import PromptTemplate
from langchain.docstore.document import Document
from langchain.chains.summarize import load_summarize_chain
from .gpt_core.chatbot_with_lock import get_token_count


class SummarizeLog:
    """
    Summarize conversation log.
    """

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

    def __init__(self, llm):
        self.llm = llm
        self.chain = load_summarize_chain(
            llm,
            chain_type="refine",
            verbose=False,
            refine_prompt=self.PROMPT_COMB,
            question_prompt=self.PROMPT_INIT,
        )
        self.user_id_map = {}

    async def mapping_user(self, bot: Bot, text: str) -> str:
        """将用户ID映射到用户昵称

        Args:
            bot (Bot): Bot
            text (str): 文本

        Returns:
            str: 映射后的文本
        """
        for user_id, user_name in self.user_id_map.items():
            user_name = "ID " + str(user_name)
            text = text.replace(
                user_name,
                f"{(await bot.get_stranger_info(user_id=int(user_id)))['user_name']}({user_id})",
            )
        return text

    async def summarize_message(self, bot: Bot, msgs: Sequence[MessageRecord]) -> str:
        """生成一段对话的总结

        Args:
            bot (Bot): Bot
            msgs (Sequence[MessageRecord]): 对话记录
            user_id_map (dict | None, optional): 用户ID映射表. Defaults to None.
            part (int | None, optional): 用于分段总结. Defaults to None.

        Returns:
            str: 总结
        """

        self.user_id_map = {msgs[0].bot_id: 0}
        for msg in msgs:
            if msg.user_id not in self.user_id_map:
                self.user_id_map[msg.user_id] = len(self.user_id_map)

        conversation_log = []
        t = ""
        for msg in msgs:
            message = repr((deserialize_message(msg.message, V11Msg)))
            if (
                msg.type == "s"
                and "用词最不友善ID的是" in message
                and "感情" in message
                and "主题" in message
            ):
                continue
            j = self.user_id_map[msg.user_id if msg.type == "r" else msg.bot_id]
            t += f"ID:{j},MsgID:{msg.message_id}\n{message}\n\n"
            if get_token_count(t) > 2000:
                conversation_log.append(t.strip())
                t = ""
        if t.strip():
            conversation_log.append(t.strip())

        content = await self.chain.arun(
            input_documents=[Document(page_content=c) for c in conversation_log]
        )

        await self.llm.reset()
        return (
            f"一共处理了{len(msgs)}条消息\n\n" + await self.mapping_user(bot, content)
        ).strip()
