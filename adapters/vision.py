"""视觉适配器：把用户发来的图片变成我能读进去的文本。

三层能力，按代价从低到高：
1. 图片基础信息（尺寸/格式）—— 纯本地，PIL。
2. 本地 OCR（Windows.Media.Ocr，离线免费，中文语言包已就位）。
3. 视觉大模型（可选，需要 config 里配 vision.model；DeepSeek 主线不支持图像）。

上层只调用 inspect()，拿到的是一段可以直接塞进提示词的中文描述。
"""

import asyncio
import os
import re
import urllib.request

MAX_BYTES = 8 * 1024 * 1024
_CJK_GAP = re.compile(r"(?<=[\u4e00-\u9fff]) (?=[\u4e00-\u9fff])")


class VisionAdapter:
    name = "vision"

    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.ocr_enabled = bool(cfg.get("ocr_enabled", True))
        self.ocr_language = cfg.get("ocr_language", "zh-Hans-CN")
        self.max_chars = int(cfg.get("max_chars", 800))
        self._ocr_engine = None

    def capabilities(self) -> list[str]:
        return ["vision_ocr"]

    # ---- 取图 ----
    def fetch(self, src: str, save_dir: str = "data/images") -> str:
        """src 可以是 http(s) URL、file:// 或本地路径；返回本地文件路径。"""
        if src.startswith("file://"):
            return src[7:]
        if not src.startswith(("http://", "https://")):
            if os.path.isfile(src):
                return src
            raise FileNotFoundError(src)
        os.makedirs(save_dir, exist_ok=True)
        ext = os.path.splitext(src.split("?")[0])[1].lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
            ext = ".png"
        out = os.path.join(save_dir, f"in_{abs(hash(src)) % 10**12}{ext}")
        if os.path.isfile(out) and os.path.getsize(out) > 0:
            return out
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0 Resident/0.9"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read(MAX_BYTES)
        if not data:
            raise ValueError("图片为空")
        with open(out, "wb") as f:
            f.write(data)
        return out

    # ---- 本地信息 + OCR ----
    def basics(self, path: str) -> str:
        try:
            from PIL import Image

            with Image.open(path) as im:
                return f"{im.width}×{im.height} {im.format or ''} {im.mode}".strip()
        except Exception as exc:
            return f"（读不出图片信息：{exc}）"

    def _engine(self):
        if self._ocr_engine is not None:
            return self._ocr_engine
        from winsdk.windows.globalization import Language
        from winsdk.windows.media.ocr import OcrEngine

        eng = None
        try:
            eng = OcrEngine.try_create_from_language(Language(self.ocr_language))
        except Exception:
            eng = None
        if eng is None:
            eng = OcrEngine.try_create_from_user_profile_languages()
        self._ocr_engine = eng
        return eng

    async def ocr(self, path: str) -> str:
        if not self.ocr_enabled:
            return ""
        engine = self._engine()
        if engine is None:
            return ""
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.storage import FileAccessMode, StorageFile

        f = await StorageFile.get_file_from_path_async(os.path.abspath(path))
        stream = await f.open_async(FileAccessMode.READ)
        decoder = await BitmapDecoder.create_async(stream)
        bmp = await decoder.get_software_bitmap_async()
        res = await engine.recognize_async(bmp)
        lines = [ln.text for ln in res.lines if ln.text.strip()]
        text = "\n".join(lines)
        # Windows OCR 会给每个汉字塞空格，收拢一下更像人话
        text = _CJK_GAP.sub("", text)
        text = re.sub(r"[ \t]{2,}", " ", text).strip()
        return text[: self.max_chars]

    async def inspect(self, src: str) -> dict:
        """返回 {path, basics, ocr}；任何一步失败都只影响该项。"""
        info = {"path": "", "basics": "", "ocr": ""}
        try:
            info["path"] = self.fetch(src)
        except Exception as exc:
            info["basics"] = f"（图片没取到：{exc}）"
            return info
        info["basics"] = self.basics(info["path"])
        try:
            info["ocr"] = await self.ocr(info["path"])
        except Exception as exc:
            info["ocr"] = f"（OCR 失败：{exc}）"
        return info

    @staticmethod
    def to_prompt(info: dict) -> str:
        """把 inspect 结果拼成一段可以直接读的中文说明。"""
        parts = [f"[图片] {info.get('basics', '')}".strip()]
        ocr = (info.get("ocr") or "").strip()
        if ocr:
            parts.append(f"[图里的文字]\n{ocr}")
        else:
            parts.append("[图里的文字] 没识别到文字")
        return "\n".join(parts)
