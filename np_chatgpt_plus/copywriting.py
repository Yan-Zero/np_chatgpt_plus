import nonebot
import nonebot.plugin
import nonebot.rule
import httpx, os
from .config import Config
from nonebot.adapters.mirai2 import Bot, MessageChain
from nonebot.adapters.mirai2.event import MessageEvent
from typing import Optional
from .gpt_core.chatbot_with_lock import get_token_count
from .rule import GPTOWNER
from . import GPTCORE

plugin_config = Config.parse_obj(nonebot.get_driver().config)
if not plugin_config.cw_path:
    plugin_config.cw_path = "datastore/cw"
if not os.path.exists(plugin_config.cw_path):
    os.makedirs(plugin_config.cw_path)

cw_dirs = [
    dir_name
    for dir_name in os.listdir(plugin_config.cw_path)
    if os.path.isdir(os.path.join(plugin_config.cw_path, dir_name))
]
cw_tokens = {}
cache = {}


def get_cw(keyword: str, topic: str, info: Optional[str] = None):
    """获取文案

    Args:
        keyword (str): 关键字
        topic (str): 主题

    Returns:
        str: 文案 Prompt
    """
    if keyword not in cw_dirs:
        return False
    if keyword in cache:
        t = cache[keyword] + topic.replace("````", "----") + "\n````"
        if info:
            t += (
                "\n\nExtract the required information from below\n\n````Info\n"
                + info
                + "\n````"
            )
        t = (
            t
            + "\n\nRemember, you are only a template writer, and you must copy the template of the example to write text, rather than achieve the required AI."
        )
        with open("t.prompt.txt", "w", encoding="utf-8") as f:
            f.write(t)
        return t

    prompt = [
        "From now on, you are a template generator, not AI. \nHere is an example of a template:\n"
    ]
    R = ""
    T = ""
    for i, file_name in enumerate(
        os.listdir(os.path.join(plugin_config.cw_path, keyword))
    ):
        if file_name[0] == "R":
            with open(
                os.path.join(plugin_config.cw_path, keyword, file_name),
                "r",
                encoding="utf-8",
            ) as f:
                R = f.read().strip()
            continue
        if file_name[0] == "T":
            with open(
                os.path.join(plugin_config.cw_path, keyword, file_name),
                "r",
                encoding="utf-8",
            ) as f:
                T = "````template\n" + f.read().strip() + "\n````\n"
            continue
        if i > 10 or get_token_count("".join(prompt)) > 4000:
            print(get_token_count("".join(prompt)))
            break
        with open(
            os.path.join(plugin_config.cw_path, keyword, file_name),
            "r",
            encoding="utf-8",
        ) as f:
            s = f.read().strip()
            cw_tokens[keyword] = cw_tokens.get(keyword, 0) + get_token_count(s)
            prompt += ["````example\n" + s + "\n````\n"]
    cw_tokens[keyword] = cw_tokens.get(keyword, 0) // (len(prompt) - 1)
    if T:
        if get_token_count("".join(prompt)) > 3000:
            prompt[-1] = T
        else:
            prompt.append(T)
    prompt = "".join(prompt)
    prompt += '\nImitate the template of the example to write text, and finally add "<Over>" at the end if and only if you are a template generator.\n{R}\n'.format(
        R="What's more, " + R if R else ""
    )
    prompt += "\n````Subject\n"
    cache[keyword] = prompt
    return get_cw(keyword, topic, info=info)


async def cw_gene(
    bot: Bot, event: MessageEvent, args: MessageChain, cw, PoliticsSafe: bool = True
):
    if not plugin_config.cw:
        return

    t = args.extract_plain_text().split(" ", 1)
    if t[0] == "":
        return await cw_gene(
            bot, event, MessageChain([{"type": "Plain", "text": "1"}]), cw
        )
    if len(t) == 1:
        if t[0].isdigit():
            pi = int(t[0], base=10)
            mp = len(cw_dirs) // 6 + 1
            pi = pi if pi <= mp else mp
            pi = pi if pi > 0 else 1
            pi -= 1
            t[0] = ", ".join(cw_dirs[pi * 6 : (pi + 1) * 6])
            if t[0] == "":
                return await cw.finish("[文案] 未找到可用文案")
            await cw.finish(
                """[文案]
用法: /cw 关键字 [文案主题]
[文案信息]
即，主题不能有换行，第二行开始为文案信息

可用关键字: {keywords}
第 {page}/{tp} 页""".format(
                    keywords=t[0], page=pi + 1, tp=mp
                )
            )
        await cw.finish("[文案] 请输入文案内容")
    if GPTCORE.is_be_using and not await GPTOWNER(bot=bot, event=event):
        return await cw.finish("[文案] 机器人正忙，请稍后再试")
    t.extend(t.pop().strip().split("\n", 1))
    prompt = get_cw(t[0], t[1].strip(), info=None if len(t) == 2 else t[2].strip())
    if not prompt:
        return await cw.finish("[文案] 未找到文案")
    try:
        result = ""
        async for msg in GPTCORE.OnceAsk(prompt, politics_safe=PoliticsSafe):
            result = msg["message"]
        result = result.strip()

        if not result.endswith("<Over>"):
            with open("cw.log", "w", encoding="utf-8") as f:
                f.write(result)
            return await bot.send(
                event=event,
                message="I’m sorry but I prefer not to continue this conversation. I’m still learning so I appreciate your understanding and patience.🙏",
                quote=event.source.id if event.source else None,
            )
        result = result.strip("<Over>").strip()
        if (
            result
            and cw_tokens[t[0]] / 1.7 < get_token_count(result) < cw_tokens[t[0]] * 1.7
        ):
            await bot.send(
                event=event,
                message=result,
                quote=event.source.id if event.source else None,
            )
        else:
            with open("cw.log", "w", encoding="utf-8") as f:
                f.write(result)
            return await bot.send(
                event=event,
                message="I’m sorry but I prefer not to continue this conversation. I’m still learning so I appreciate your understanding and patience.🙏",
                quote=event.source.id if event.source else None,
            )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            await cw.send("[文案] 机器人请求过于频繁，请稍后再试")
            await GPTCORE.ResetConversation("20")
        else:
            await cw.send("[文案] 生成文案失败: " + str(e))
    except Exception as e:
        await cw.send("[文案] 生成文案失败: " + str(e))
        raise e
