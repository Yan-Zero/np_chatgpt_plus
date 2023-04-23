from pydantic import BaseModel, Extra
import os
from typing import List, Optional, Set


class Config(BaseModel, extra=Extra.ignore):
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
