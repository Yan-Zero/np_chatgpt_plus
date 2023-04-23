from pydantic import BaseModel, Extra


class Config(BaseModel, extra=Extra.ignore):
    """Plugin Config Here"""


from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="ChatGPT Plus",
    description="利用 ChatGPT 来实现各种功能",
    usage="要有 ChatGPT Plus 的 access_token 才能使用",
    config=Config,
    extra={},
)
