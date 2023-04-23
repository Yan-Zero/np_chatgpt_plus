import base64
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Type, Union, overload

from nonebot_plugin_datastore import get_plugin_data
from nonebot.adapters.mirai2.message import MessageChain

JsonMsg = List[Dict[str, Any]]

def deserialize_message(msg: JsonMsg):
    return MessageChain(msg)

def simplify_message(msg: MessageChain, desc: bool = False) -> str:
    result = ""
    for i in msg:
        # result += str(i)

        if i.type == "Plain":
            result += i.data["text"]
        elif i.type == "Image":
            result += f"\n![Image]({i.data['url']})\n"
        elif i.type == "Voice":
            result += "[Voice]"
        elif i.type == "At":
            result += f"@{i.data['target']}"
        elif i.type == "AtAll":
            result += "@全体成员"
        elif i.type == "Face":
            result += f"[Face {i.data['name']}]"
        elif i.type == "FlashImage":
            result += "[FlashImage]"
        elif i.type == "Xml":
            result += f"[{i.data['xml']}]"
        elif i.type == "Json":
            result += f"[{i.data['json']}]"
        elif i.type == "App":
            result += f"[App {i.data['content']}]"
        elif i.type == "Poke":
            result += f"[戳一戳 {i.data['name']}]"
        elif i.type == "Quote":
            result += f"[Quote MsgID:{i.data['id']}{' Msg:' if desc else ''}{simplify_message(i.data['origin'], desc) if desc else ''} ]\n"
        elif i.type == "Forward":
            result += f"[Forward]\n"
        elif i.type == "File":
            result += f"[File {i.data['name']} {i.data['size']}]"
        elif i.type == "MusicShare":
            result += f"[Music {i.data['title']} {i.data['summary']}]"
        elif i.type == "Dice":
            result += f"[Dice {i.data['value']}]"
        elif i.type == "MarketFace":
            result += f"[Face {i.data['name']}]"
        else:
            result += f"[Unkown {i.type}]"
    return result
    