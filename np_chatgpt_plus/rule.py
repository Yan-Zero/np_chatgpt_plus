import nonebot
from nonebot.adapters import Bot, Event
from nonebot.internal.permission import USER as USER
from nonebot.internal.permission import User as User
from nonebot.internal.permission import Permission as Permission
from .config import Config
from nonebot_plugin_datastore import get_plugin_data, create_session

plugin_data = get_plugin_data()
global_config = nonebot.get_driver().config
plugin_config = Config.parse_obj(global_config)

__cached = {}


class Ban(Permission):
    """检查当前事件是否是消息事件且属于被封禁的人"""

    __slots__ = ()

    def __repr__(self) -> str:
        return "Ban()"

    async def __call__(self, bot: Bot, event: Event) -> bool:
        try:
            user_id = event.get_user_id()
        except Exception:
            return False
        return (
            f"{bot.adapter.get_name().split(maxsplit=1)[0].lower()}:{user_id}"
            in await plugin_data.config.get("ban", ())
            or user_id in await plugin_data.config.get("ban", ())  # 兼容旧配置
        )


class RequestLimit(Permission):
    """检查当前事件是否是消息事件且属于次数已经超过限制"""

    __slots__ = ()

    def __repr__(self) -> str:
        return "RequestLimit()"

    async def __call__(self, bot: Bot, event: Event) -> bool:
        global __cached
        try:
            user_id = event.get_user_id()
        except Exception:
            return False
        return (await plugin_data.config.get("request_limit", {})).get(
            f"{bot.adapter.get_name().split(maxsplit=1)[0].lower()}:{user_id}", 0
        ) < plugin_config.request_limit


COUNT_LIMIT = Permission(RequestLimit())
"""匹配请求次数超过限制的用户事件"""

BAN: Permission = Permission(Ban())
"""匹配封禁用户事件"""


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
