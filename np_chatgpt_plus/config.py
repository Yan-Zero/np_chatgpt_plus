from pydantic import BaseModel, Extra
import os


class Config(BaseModel, extra=Extra.ignore):
    """Plugin Config Here"""

    cw: bool = True
    cw_path: str = "datastore/cw"

    # 每个群组最大消息记录数
    max_length: int = 75
    collect_analytics: bool = False
    paid: bool = False
    access_token: str = os.getenv("CHATGPT_ACCESS_TOKEN", "")
    model: str = "text-davinci-002-render-sha"
    puid: str = os.getenv("PUID", "")

    chat: bool = True
    """是否启用 ChatGPT 功能"""
    gpt_owner: list[str] = []
    request_limit: int = 20
    """每个用户每天最多请求次数"""
    proxy: str = ""
    cf_clearance: str = ""
    cf_clearance_ua: str = ""


from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="ChatGPT Plus",
    description="利用 ChatGPT 来实现各种功能",
    usage="要有 ChatGPT Plus 的 access_token 才能使用",
    config=Config,
    extra={},
)
