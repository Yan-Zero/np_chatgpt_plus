import asyncio, re, tiktoken, uuid
from revChatGPT.V1 import Chatbot, AsyncChatbot
from typing import Optional


def get_code_from_markdown(md: str) -> list[str]:
    result = re.search(r"```(?:.*)\n([\s\S]*?)\n```", md, flags=re.MULTILINE)
    if result:
        return [re.sub(r"(```\s*\w*\n)|(```)", "", x) for x in result.groups()]
    else:
        return []


def construct_message(msg, role="user", name=None, content_type="text"):
    msg = {
        "id": str(uuid.uuid4()),
        "author": {
            "role": role,
            "name": name,
        },
        "content": {"content_type": content_type, "parts": [msg]},
        "end_turn": True,
    }
    return msg


class ChatbotWithLock:
    config: dict
    cb_map: dict
    now_model: str

    def __init__(
        self,
        config,
        conversation_id=None,
        parent_id=None,
    ):
        self.now_model = config["model"]
        self.default_model = config["model"]
        self.config = {self.default_model: config}
        self.lock = asyncio.Lock()
        self.cb_map = {}
        self.chatbot = Chatbot(config, conversation_id, parent_id)

    def __post(
        self, messages, conversation_id, parent_id, auto_continue, timeout, model
    ):
        new_model = self.default_model if model == None else model
        if (
            conversation_id != self.conversation_id and self.conversation_id
        ) or new_model != self.now_model:
            self.cb_map[self.conversation_id] = self.chatbot
            if conversation_id in self.cb_map and new_model == self.now_model:
                self.chatbot = self.cb_map[conversation_id]
            else:
                self.now_model = new_model
                if self.now_model not in self.config:
                    self.config[self.now_model] = self.config[self.default_model].copy()
                    self.config[self.now_model]["model"] = self.now_model
                self.chatbot = Chatbot(
                    self.config[self.now_model], conversation_id, parent_id
                )
        for i in self.chatbot.post_messages(messages, conversation_id=conversation_id, parent_id=parent_id, model=model, auto_continue=auto_continue, timeout=timeout):  # type: ignore
            yield i

    async def ask(
        self,
        prompt: str,
        conversation_id=None,
        parent_id=None,
        timeout: int = 360,
        auto_continue: bool = False,
        model: Optional[str] = None,
    ):
        async with self.lock:
            for i in self.__post(
                [construct_message(prompt)],
                conversation_id,
                parent_id,
                auto_continue,
                timeout,
                model,
            ):
                yield i

    async def post(
        self,
        messages: list,
        conversation_id=None,
        parent_id=None,
        timeout: int = 360,
        auto_continue: bool = False,
        model: Optional[str] = None,
    ):
        async with self.lock:
            for i in self.__post(
                messages, conversation_id, parent_id, auto_continue, timeout, model
            ):
                yield i

    async def continue_write(
        self,
        conversation_id: str | None = None,
        parent_id: str | None = None,
        timeout: int = 360,
    ):
        async with self.lock:
            for i in self.chatbot.continue_write(conversation_id, parent_id, timeout):  # type: ignore
                yield i

    async def get_conversations(self, offset: int = 20, limit: int = 20):
        async with self.lock:
            return self.chatbot.get_conversations(offset, limit)

    async def get_msg_history(self, convo_id, encoding=None):
        async with self.lock:
            return self.chatbot.get_msg_history(convo_id, encoding)

    async def gen_title(self, convo_id, message_id):
        async with self.lock:
            return self.chatbot.gen_title(convo_id, message_id)

    async def change_title(self, convo_id, title):
        async with self.lock:
            return self.chatbot.change_title(convo_id, title)

    async def delete_conversation(self, convo_id):
        async with self.lock:
            if convo_id:
                if self.conversation_id == convo_id:
                    self.chatbot = Chatbot(self.config[self.now_model])
                if self.conversation_id in self.cb_map:
                    del self.cb_map[self.conversation_id]
                return self.chatbot.delete_conversation(convo_id)
            else:
                return {}

    async def clear_conversations(self):
        async with self.lock:
            self.cb_map = {}
            return self.chatbot.clear_conversations()

    @property
    def conversation_id(self):
        return self.chatbot.conversation_id

    async def set_conversation_id(self, value):
        async with self.lock:
            self.chatbot.conversation_id = value

    @property
    def parent_id(self):
        return self.chatbot.parent_id

    async def set_parent_id(self, value):
        async with self.lock:
            self.chatbot.parent_id = value

    @property
    def is_locked(self):
        return self.lock.locked()

    @property
    def recipients(self):
        return self.chatbot.recipients


class AsyncChatbotWithLock(ChatbotWithLock):
    def __init__(
        self,
        config,
        conversation_id=None,
        parent_id="",
    ):
        super().__init__(config, conversation_id, parent_id)
        self.chatbot = AsyncChatbot(config, conversation_id, parent_id)

    async def __post(
        self, messages, conversation_id, parent_id, auto_continue, timeout, model
    ):
        new_model = self.default_model if not model else model
        if (
            conversation_id != self.conversation_id and self.conversation_id
        ) or new_model != self.now_model:
            self.cb_map[self.conversation_id] = self.chatbot
            if conversation_id in self.cb_map and new_model == self.now_model:
                self.chatbot = self.cb_map[conversation_id]
            else:
                self.now_model = new_model
                if self.now_model not in self.config:
                    self.config[self.now_model] = self.config[self.default_model].copy()
                    self.config[self.now_model]["model"] = self.now_model
                self.chatbot = AsyncChatbot(
                    self.config[self.now_model], conversation_id, parent_id
                )
        async for i in self.chatbot.post_messages(messages, conversation_id=conversation_id, parent_id=parent_id, model=model, auto_continue=auto_continue, timeout=timeout):  # type: ignore
            yield i

    async def ask(
        self,
        prompt: str,
        conversation_id=None,
        parent_id=None,
        timeout: int = 360,
        auto_continue: bool = False,
        model: Optional[str] = None,
    ):
        async with self.lock:
            async for i in self.__post(
                [construct_message(prompt)],
                conversation_id,
                parent_id,
                auto_continue,
                timeout,
                model,
            ):
                yield i

    async def post(
        self,
        messages: list,
        conversation_id=None,
        parent_id=None,
        timeout: int = 360,
        auto_continue: bool = False,
        model: Optional[str] = None,
    ):
        async with self.lock:
            async for i in self.__post(
                messages, conversation_id, parent_id, auto_continue, timeout, model
            ):
                yield i

    async def continue_write(
        self,
        conversation_id: str | None = None,
        parent_id: str | None = None,
        timeout: int = 360,
    ):
        async with self.lock:
            async for i in self.chatbot.continue_write(conversation_id, parent_id, timeout):  # type: ignore
                yield i

    async def get_conversations(self, offset: int = 20, limit: int = 20):
        async with self.lock:
            return await self.chatbot.get_conversations(offset, limit)

    async def get_msg_history(self, convo_id, encoding=None):
        async with self.lock:
            return await self.chatbot.get_msg_history(convo_id, encoding)

    async def gen_title(self, convo_id, message_id):
        async with self.lock:
            return await self.chatbot.gen_title(convo_id, message_id)

    async def change_title(self, convo_id, title):
        async with self.lock:
            return await self.chatbot.change_title(convo_id, title)

    async def delete_conversation(self, convo_id):
        async with self.lock:
            if convo_id:
                if self.conversation_id == convo_id:
                    self.chatbot = AsyncChatbot(self.config[self.now_model])
                if self.conversation_id in self.cb_map:
                    del self.cb_map[self.conversation_id]
                return await self.chatbot.delete_conversation(convo_id)
            else:
                return {}

    async def clear_conversations(self):
        async with self.lock:
            self.cb_map = {}
            return await self.chatbot.clear_conversations()


def tokenize(prompt: str, model: str = "gpt-3.5-turbo") -> list[int]:
    """Tokenize a prompt"""
    tiktoken.model.MODEL_PREFIX_TO_ENCODING["gpt-4-"] = "cl100k_base"
    tiktoken.model.MODEL_TO_ENCODING["gpt-4"] = "cl100k_base"

    encoding = tiktoken.encoding_for_model(model)
    return encoding.encode(prompt)


# https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
def get_token_count(prompt: str, model: str = "gpt-3.5-turbo") -> int:
    """Get the token count of a prompt"""
    return len(tokenize(prompt, model)) + 10


from nonebot.adapters import Bot, Event
from nonebot.internal.permission import USER as USER
from nonebot.internal.permission import User as User
from nonebot.internal.permission import Permission as Permission
import nonebot
from .config import Config

global_config = nonebot.get_driver().config
plugin_config = Config.parse_obj(global_config)


class GPTOwner(Permission):
    """检查当前事件是否是消息事件且属于 GPT 超级用户。"""

    __slots__ = ()

    def __repr__(self) -> str:
        return "Superuser()"

    async def __call__(self, bot: Bot, event: Event) -> bool:
        try:
            user_id = event.get_user_id()
        except Exception:
            return False
        return (
            f"{bot.adapter.get_name().split(maxsplit=1)[0].lower()}:{user_id}"
            in plugin_config.gpt_owner
            or user_id in plugin_config.gpt_owner  # 兼容旧配置
        )


GPTOWNER: Permission = Permission(GPTOwner())
"""匹配 GPT 超级用户事件"""
