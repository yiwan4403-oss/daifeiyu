import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageDraw

img = Image.new("RGB", (200, 120), "white")
d = ImageDraw.Draw(img)
d.text((60, 45), "42", fill="black")
img.save(".vision_test.png")

from main import load_config, make_components  # noqa: E402
from core.agent import ResidentAgent  # noqa: E402
from identity.emotion import EmotionManager  # noqa: E402

out = []


async def run():
    cfg = load_config("config.yaml")
    c = make_components(cfg)
    c["identity"].ensure_default()
    c["emotion"] = EmotionManager(c["conn"])
    a = ResidentAgent(cfg, c)
    img_url = "file:///" + os.path.abspath(".vision_test.png").replace("\\", "/")
    prompt = a._with_images("图里写的数字是多少？", [img_url])
    if isinstance(prompt, list):
        part = prompt[0]
        out.append("prompt 是列表，首元素类型: " + type(part).__name__)
        url = getattr(part, "url", "")
        out.append(f"data uri 长度: {len(url)} 前缀: {url[:40]}")
    else:
        out.append("prompt 是文本: " + str(prompt))
    try:
        reply = await a.chat("图里写的数字是多少？只回答数字。", "chat", user_key="test", images=[img_url])
        out.append("她 > " + reply)
        out.append("usage: " + str(a.conn.execute("SELECT in_tokens,out_tokens FROM model_usage ORDER BY id DESC LIMIT 1").fetchone()))
    except Exception as e:
        out.append("ERR: " + type(e).__name__ + " " + str(e)[:300])
    c["conn"].close()


asyncio.run(run())
os.remove(".vision_test.png")
open(".v2.txt", "w", encoding="utf-8").write("\n".join(out))
