# core/ear.py
"""
耳 — 音を聴けるモデルに、そのターンの間だけ担当を替えるための部品。

何をするものか:
    住人（柚月）が「聴く」と決めたターンだけ、LLM を音の聴けるモデル（最初は Qwen3.8-Omni-Flash）に
    替える。ターンが終われば仕組みが必ず元の LLM に戻す（core/agent.py の process_message の出口）。
    住人への約束は「聴ける」ことで、モデルの名前は約束に入れない。差し替えは設定だけで済む。

ここにあるもの:
    - 設定の読み込み（config.yaml / settings.json の `ear:`。既定は無効＝何も起きない）
    - 耳用のプロバイダの生成（既存の OpenAICompatibleProvider をそのまま使う）
    - 耳のモデルの数え方でのトークン計数（トークナイザーが違えば同じ文脈でも数が変わる）
    - 音のファイルの読み込みと、履歴の中の「音の参照」の描き分け

履歴に音そのものは置かない:
    履歴に入れるのは {"type": "audio_ref", "path": ..., "turn": ...} という軽い参照だけ。
    送る直前（ContextBuilder._filter_conversation_history）に、
      - いま耳を借りているターンの参照 → 本物の音（input_audio）
      - それ以外（元の LLM へ送るとき・過去のターンの参照）→ 「ここでこの音を聴いた」という一文
    に描き分ける。こうすると状態ファイルに数 MB の base64 が残らず、途中で落ちて再起動しても
    音を受け付けない LLM に音が送られることがない（既定が「一文」なので、耳を知らない呼び出し元は安全側）。

設計と実測は docs/GEMINI_EAR_DESIGN.md。
"""

import base64
import os
import time
import wave
from pathlib import Path
from typing import Optional

from core.i18n import t
from core.time_utils import tlog

# 音の参照の型名（会話履歴の content リストに入る部品）
AUDIO_REF_TYPE = "audio_ref"

# 受け付ける拡張子 → API に渡す format 名
_FORMATS = {".mp3": "mp3", ".wav": "wav"}

# 1 ファイルの上限（バイト）。base64 にすると 4/3 倍になる。
# Qwen は data-uri 1 つが 20,971,520 バイトまで（2026-09-20 実測: 14MB の wav は通り、19MB は 413）。
# 15,000,000 バイト → base64 で 20,000,000。224kbps の mp3 なら 9 分弱。
_DEFAULT_MAX_BYTES = 15_000_000

_DEFAULTS = {
    "enabled": False,
    "provider": "qwen",
    "base_url": "https://maas.qwencloudapi.com/compatible-mode/v1",
    "model": "qwen3.8-omni-flash",
    # 住人の普段と同じ思考オフ。Qwen は既定が思考ありで、思考ありの 80 万トークンでは
    # 入力検査の誤判定が出た（2026-09-20 実測）
    "thinking": "off",
    # 入力＋出力の枠の上限。Qwen3.8-Omni-Flash は入力 991,808（思考オフ）・文脈 1M。
    # 出力枠 16,384 を足して 1,000,000 に収める＝入力は 983,616 まで
    "context_limit": 1_000_000,
    "tokenizer_path": "data/tokenizer_qwen.json",
    "max_audio_bytes": _DEFAULT_MAX_BYTES,
    # 音 1 秒あたりのトークンの見積もり（Qwen の実測は約 7・Gemini は約 26〜32。設定で上書きする）
    "audio_tokens_per_second": 10,
    # 音の data の書き方。Qwen は "data:;base64,..."（data URI）、Gemini は素の base64
    "audio_data_uri": True,
    # 429（短時間のトークン量の上限）のとき、待って送り直す回数と待ち時間（秒）
    "retry_429": 2,
    "retry_429_wait": 35,
}

_config_cache: tuple[float, dict] = (0.0, {})
_config_stamp: tuple = ()


def _config_files_stamp() -> tuple:
    """設定ファイル（config.yaml / settings.json）の更新時刻と大きさ。読み直すかどうかの判断に使う。"""
    try:
        from core.paths import config_yaml_path
        paths = [str(config_yaml_path())]
    except Exception:
        paths = ["config.yaml"]
    try:
        # 実際に load_config が読むのは data-root の settings.json（配布版は作業フォルダと別の場所）
        from core.paths import settings_path
        paths.append(str(settings_path()))
    except Exception:
        paths.append("settings.json")
    stamp = []
    for path in paths:
        try:
            st = os.stat(path)
            stamp.append((path, st.st_mtime_ns, st.st_size))
        except OSError:
            stamp.append((path, 0, 0))
    return tuple(stamp)


def load_ear_config(force: bool = False) -> dict:
    """`ear:` の設定を既定値と合わせて返す。

    道具の定義の組み立て（＝耳を使わない普段のターンも含む毎回の LLM 呼び出し）から呼ばれるので、
    設定ファイルが変わっていない限り読み直さない（更新時刻を見るだけ）。耳が無効の配布版でも、
    普段のターンに設定全体の読み込みを足さないため。
    """
    global _config_cache, _config_stamp
    now = time.monotonic()
    stamp = _config_files_stamp()
    if not force and _config_cache[1] and stamp == _config_stamp:
        return _config_cache[1]
    _config_stamp = stamp
    cfg = dict(_DEFAULTS)
    try:
        from core.config_loader import load_config
        user = load_config().get("ear") or {}
        if isinstance(user, dict):
            cfg.update({k: v for k, v in user.items() if v is not None})
    except Exception as e:
        tlog(f"[Ear] 設定を読めませんでした（無効として扱います）: {e}")
        cfg["enabled"] = False
    _config_cache = (now, cfg)
    return cfg


def _api_key(cfg: dict) -> str:
    name = str(cfg.get("provider") or "").upper()
    return os.environ.get(f"CG_LLM_{name}_API_KEY", "") or os.environ.get(f"{name}_API_KEY", "")


def is_enabled() -> bool:
    """耳が使える状態か（設定で有効、かつ鍵がある）。無効なら道具の定義にも出さない。"""
    cfg = load_ear_config()
    return bool(cfg.get("enabled")) and bool(_api_key(cfg))


# --- 耳のモデルの数え方 ---

class EarTokenCounter:
    """耳のモデルのトークナイザーでメッセージを数える。

    トークナイザーが違えば同じ文脈でもトークン数が変わる（住人の日本語は DeepSeek 比で Qwen 90%・
    ツール結果は逆に 101%。2026-09-20 実測）。元の LLM の使用率から推し量らず、必ず相手の数え方で数える。
    トークナイザーのファイルが無いときは core/tokens.py（元の LLM の数え方）で代用する。
    """

    _CACHE_MIN_LEN = 200
    _CACHE_MAX_CHARS = 20_000_000

    def __init__(self, tokenizer_path: str, audio_tokens_per_second: float = 10):
        self._path = tokenizer_path
        self._tok = None
        self._tried = False
        self._cache: dict[str, int] = {}
        self._cache_chars = 0
        self._audio_tps = float(audio_tokens_per_second or 10)

    def _ensure(self):
        if self._tried:
            return
        self._tried = True
        try:
            from tokenizers import Tokenizer
            from core.paths import resolve_path
            p = str(resolve_path(self._path))
            if os.path.isfile(p):
                self._tok = Tokenizer.from_file(p)
                tlog(f"[Ear] 耳のモデルのトークナイザーを読み込みました ({self._path})")
            else:
                tlog(f"[Ear] {self._path} が無いため、元の LLM の数え方で代用します")
        except Exception as e:
            tlog(f"[Ear] トークナイザーの読み込みに失敗（元の LLM の数え方で代用）: {e}")

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        self._ensure()
        if self._tok is None:
            from core.tokens import count_text_tokens
            return count_text_tokens(text)
        if len(text) < self._CACHE_MIN_LEN:
            return len(self._tok.encode(text, add_special_tokens=False).ids)
        hit = self._cache.get(text)
        if hit is not None:
            return hit
        n = len(self._tok.encode(text, add_special_tokens=False).ids)
        if self._cache_chars + len(text) > self._CACHE_MAX_CHARS:
            self._cache.clear()
            self._cache_chars = 0
        self._cache[text] = n
        self._cache_chars += len(text)
        return n

    def count_messages(self, messages: list) -> int:
        from core.tokens import _get_tokens_per_image
        total = 0
        for m in messages:
            total += 4
            c = m.get("content")
            if isinstance(c, str):
                total += self.count_text(c)
            elif isinstance(c, list):
                for part in c:
                    if not isinstance(part, dict):
                        continue
                    kind = part.get("type")
                    if kind == "text":
                        total += self.count_text(part.get("text", ""))
                    elif kind == "image_url":
                        total += _get_tokens_per_image()
                    elif kind == "input_audio":
                        data = (part.get("input_audio") or {}).get("data") or ""
                        total += int(_AUDIO_SECONDS.get(id(data), 0) * self._audio_tps) or self._audio_by_size(data)
                    elif kind == AUDIO_REF_TYPE:
                        total += int(float(part.get("seconds") or 0) * self._audio_tps) or 2000
            for tc in m.get("tool_calls") or []:
                f = tc.get("function", {})
                total += self.count_text(f.get("name", "")) + self.count_text(f.get("arguments", ""))
        return total

    def _audio_by_size(self, data: str) -> int:
        # 長さが分からない音は大きさから見積もる（base64 2,700 文字 ≒ 2KB ≒ 1 トークン。多めに出る）
        return max(200, len(data) // 2700)


# base64 文字列（オブジェクト）→ 秒数。数えるときに長さから見積もれるようにする覚え書き
_AUDIO_SECONDS: dict[int, float] = {}


_COUNTERS: dict[tuple, "EarTokenCounter"] = {}


def _get_counter(tokenizer_path: str, audio_tps) -> "EarTokenCounter":
    """数える部品は使い回す（トークナイザーの読み込みに約1秒・数えた結果の覚え書きも持っているため）。"""
    key = (tokenizer_path, float(audio_tps or 10))
    if key not in _COUNTERS:
        _COUNTERS[key] = EarTokenCounter(tokenizer_path, audio_tps)
    return _COUNTERS[key]


def create_ear_provider(main_llm=None):
    """耳用のプロバイダを作る。使えない状態なら None。

    クラスは既存の OpenAICompatibleProvider。温度と出力枠は元の LLM に合わせる
    （そのターンだけ話し方の設定が変わらないように）。
    """
    cfg = load_ear_config(force=True)
    key = _api_key(cfg)
    if not cfg.get("enabled") or not key:
        return None
    from core.llm import OpenAICompatibleProvider
    provider = OpenAICompatibleProvider(
        api_key=key,
        base_url=str(cfg["base_url"]),
        model=str(cfg["model"]),
        temperature=float(getattr(main_llm, "temperature", 1.0) or 1.0),
        max_tokens=int(getattr(main_llm, "max_tokens", 4096) or 4096),
        provider=str(cfg.get("provider") or ""),
        thinking=str(cfg.get("thinking") or "off"),
    )
    provider.token_counter = _get_counter(str(cfg["tokenizer_path"]), cfg.get("audio_tokens_per_second", 10))
    limit = int(cfg.get("context_limit") or 0)
    provider.context_limit_getter = (lambda: limit) if limit > 0 else None
    provider.is_ear = True
    return provider


# --- 音のファイル ---

def _audio_seconds(path: Path, fmt: str) -> float:
    """音の長さ（秒）。分からなければ 0。"""
    try:
        if fmt == "wav":
            with wave.open(str(path), "rb") as w:
                return w.getnframes() / float(w.getframerate() or 1)
        try:
            from mutagen import File as _MFile  # あれば使う（無くてもよい）
            mf = _MFile(str(path))
            if mf is not None and getattr(mf, "info", None):
                return float(mf.info.length or 0)
        except Exception:
            pass
        return _mp3_seconds(path)
    except Exception:
        return 0.0


def _mp3_seconds(path: Path) -> float:
    """MP3 の長さを先頭フレームのビットレートから見積もる（CBR 前提の概算。外れても支障はない）。"""
    rates = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            head = f.read(65536)
        start = 0
        if head[:3] == b"ID3" and len(head) >= 10:
            start = 10 + ((head[6] & 0x7F) << 21 | (head[7] & 0x7F) << 14 | (head[8] & 0x7F) << 7 | (head[9] & 0x7F))
            if start >= len(head) - 4:
                with open(path, "rb") as f:
                    f.seek(start)
                    head = f.read(8192)
                start_in = 0
            else:
                start_in = start
        else:
            start_in = 0
        for i in range(start_in, len(head) - 4):
            if head[i] == 0xFF and (head[i + 1] & 0xE0) == 0xE0:
                version = (head[i + 1] >> 3) & 0x03   # 3 = MPEG1
                layer = (head[i + 1] >> 1) & 0x03     # 1 = Layer III
                idx = (head[i + 2] >> 4) & 0x0F
                if version == 3 and layer == 1 and 0 < idx < 15:
                    kbps = rates[idx]
                    return max(0.0, (size - start) * 8 / (kbps * 1000.0))
        return 0.0
    except Exception:
        return 0.0


def describe_seconds(seconds: float) -> str:
    """「3分42秒」のような長さの言い方。分からなければ空文字。"""
    s = int(round(float(seconds or 0)))
    if s <= 0:
        return ""
    if s < 60:
        return t("ear_len_sec", s=s)
    return t("ear_len_min_sec", m=s // 60, s=s % 60)


def inspect_audio(workspace_path: str, source: str,
                  honorific: str = "ユーザー") -> tuple[Optional[dict], Optional[str]]:
    """音のファイルを確かめ、(情報, None) か (None, 住人に返す文) を返す。中身はまだ読まない。

    情報: {"path": workspace からの相対パス, "format": "mp3"/"wav", "seconds": 長さ, "bytes": 大きさ}
    返す文は道具を主語にし、次に何を打てばよいかまで書く（行き止まりにしない）。
    """
    cfg = load_ear_config()
    src = (source or "").strip()
    if not src:
        return None, t("ear_err_no_source")
    if src.startswith("http://") or src.startswith("https://"):
        return None, t("ear_err_url")
    ws = Path(workspace_path).resolve()
    rel = src.replace("\\", "/")
    if rel.startswith("workspace/"):
        rel = rel[len("workspace/"):]
    p = (ws / rel).resolve()
    try:
        inside = p.is_relative_to(ws)
    except Exception:
        inside = False
    if not inside:
        return None, t("ear_err_outside", source=src)
    if not p.is_file():
        return None, t("ear_err_not_found", source=src)
    fmt = _FORMATS.get(p.suffix.lower())
    if not fmt:
        return None, t("ear_err_format", source=src)
    size = p.stat().st_size
    limit = int(cfg.get("max_audio_bytes") or _DEFAULT_MAX_BYTES)
    if size > limit:
        # 大きさの話は住人に見せない（オーナー向けのログにだけ残す）
        tlog(f"[Ear] {src} は {size:,} バイトで、耳のモデルに一度に渡せる {limit:,} バイトに収まりません")
        return None, t("ear_err_too_big", source=src, honorific=honorific)
    rel_posix = p.relative_to(ws).as_posix()
    return {"path": rel_posix, "format": fmt, "seconds": round(_audio_seconds(p, fmt), 1), "bytes": size}, None


# 読み込んだ音の覚え書き（同じターンの中で何度も送るので、base64 を作り直さない）
_AUDIO_CACHE: dict[tuple, str] = {}
_AUDIO_CACHE_MAX = 4


def _load_audio_data(workspace_path: str, rel_path: str, seconds: float) -> Optional[str]:
    p = (Path(workspace_path) / rel_path)
    try:
        st = p.stat()
        as_uri = bool(load_ear_config().get("audio_data_uri", True))
        key = (str(p), st.st_mtime_ns, st.st_size, as_uri)
        data = _AUDIO_CACHE.get(key)
        if data is None:
            data = ("data:;base64," if as_uri else "") + base64.b64encode(p.read_bytes()).decode("ascii")
            if len(_AUDIO_CACHE) >= _AUDIO_CACHE_MAX:
                for old in list(_AUDIO_CACHE)[: len(_AUDIO_CACHE) - _AUDIO_CACHE_MAX + 1]:
                    _AUDIO_SECONDS.pop(id(_AUDIO_CACHE.pop(old)), None)
            _AUDIO_CACHE[key] = data
        _AUDIO_SECONDS[id(data)] = float(seconds or 0)
        return data
    except Exception as e:
        tlog(f"[Ear] 音のファイルを読めませんでした（一文に置き換えて送ります）: {rel_path}: {e}")
        return None


def make_audio_ref(info: dict, turn_id: str) -> dict:
    """会話履歴に置く「音の参照」の部品。

    heard は最初 False。実際に音を載せて送り、耳のモデルから応答が返って初めて True にする
    （confirm_heard）。聴く前に保存・中断・再起動が挟まっても、聴いていないものを「聴いた」と書かないため。
    """
    return {"type": AUDIO_REF_TYPE, "path": info["path"], "format": info["format"],
            "seconds": info.get("seconds") or 0, "turn": turn_id, "heard": False}


def placeholder_text(ref: dict) -> str:
    """音の参照を一文にしたもの（元の LLM へ送るとき・過去のターンの参照・保存・圧縮の入力）。"""
    if not ref.get("heard"):
        # まだ耳のモデルに届いていない音（届く前に耳を返した・ファイルを読めなかった等）
        return t("ear_unheard_placeholder", path=ref.get("path", ""))
    length = describe_seconds(ref.get("seconds") or 0)
    if length:
        return t("ear_heard_placeholder_len", path=ref.get("path", ""), length=length)
    return t("ear_heard_placeholder", path=ref.get("path", ""))


def _same_except_audio(sent_parts: list, hist_parts: list) -> bool:
    """送った content と履歴の content が、音の位置を除いて同じ並びか。

    render_audio_refs は部品の数と順番を変えず、音の参照の位置だけを input_audio か一文に置き換える。
    だから「同じ長さで、音の参照でない位置の部品が等しい」ものが、その履歴メッセージの送信用の写し。
    """
    if len(sent_parts) != len(hist_parts):
        return False
    for sp, hp in zip(sent_parts, hist_parts):
        if isinstance(hp, dict) and hp.get("type") == AUDIO_REF_TYPE:
            continue
        if isinstance(hp, dict) and hp.get("type") == "image_url":
            # 古い画像は送信用の写しでは一文に置き換わっていることがある（_limit_recent_images）。
            # いまは画像と音を同じメッセージに入れる差し込みは無いが、入れたときに確定が漏れないように
            continue
        if sp is not hp and sp != hp:
            return False
    return True


def _sent_audio_is(sent_part: dict, ref: dict) -> bool:
    """送った音の部品が、その参照の音か。読み込んだ音の覚え書きで出所が分かるときだけ確かめる
    （分からなければ位置の一致を信じる）。頭書きがまったく同じで出所の違う音が並んだときの取り違え防止。"""
    data = (sent_part.get("input_audio") or {}).get("data")
    for (path, *_rest), cached in list(_AUDIO_CACHE.items()):
        if cached is data:
            return Path(path).as_posix().endswith("/" + str(ref.get("path", "")).lstrip("/"))
    return True


def confirm_heard(sent_messages: list, history: list, live_turn: Optional[str]) -> int:
    """耳のモデルから応答が返ったあとに呼ぶ。実際に音として送った参照だけを「聴いた」にする。

    sent_messages: 実際に送った messages。history: 会話履歴。live_turn: 耳を借りているターンの印。
    覚え書きを別に持たず、送った messages そのものと履歴を位置で突き合わせる
    （覚え書きをモジュール全体で持つと、別の呼び出し元の描画で消えたり溢れたりして、
    聴いた音が「まだ耳に届いていません」のまま残る。Codex 2巡目の指摘）。
    同じターンに同じ音を先にも渡していれば、そちらも聴いた扱いにする（音そのものは後ろの1か所で耳に届いている）。
    戻り値は「聴いた」にした参照の数。
    """
    if not live_turn:
        return 0
    sent_with_audio = [m.get("content") for m in sent_messages or []
                       if isinstance(m.get("content"), list)
                       and any(isinstance(p, dict) and p.get("type") == "input_audio" for p in m["content"])]
    if not sent_with_audio:
        return 0
    heard_paths = set()
    for h in history or []:
        hc = h.get("content")
        if not isinstance(hc, list) or not any(
                isinstance(p, dict) and p.get("type") == AUDIO_REF_TYPE and p.get("turn") == live_turn for p in hc):
            continue
        for sc in sent_with_audio:
            if not _same_except_audio(sc, hc):
                continue
            for sp, hp in zip(sc, hc):
                if (isinstance(hp, dict) and hp.get("type") == AUDIO_REF_TYPE and hp.get("turn") == live_turn
                        and isinstance(sp, dict) and sp.get("type") == "input_audio" and _sent_audio_is(sp, hp)):
                    heard_paths.add(hp.get("path"))
            break
    n = 0
    for h in history or []:
        hc = h.get("content")
        if not isinstance(hc, list):
            continue
        for p in hc:
            if (isinstance(p, dict) and p.get("type") == AUDIO_REF_TYPE and not p.get("heard")
                    and p.get("turn") == live_turn and p.get("path") in heard_paths):
                p["heard"] = True
                n += 1
    return n


def render_audio_refs(messages: list, live_turn: Optional[str], workspace_path: str) -> list:
    """メッセージの中の「音の参照」を、送り先に合わせて描き分けた写しを返す。

    live_turn が一致する参照だけを本物の音にする。それ以外はすべて一文にする
    （live_turn=None なら全部一文＝音を受け付けない LLM に安全）。
    元のリスト・元のメッセージは書き換えない。音の参照が無いメッセージは同じオブジェクトを返す。
    """
    # 同じターンに同じ音を聴き直したときは、最後の1か所だけを本物の音にする。
    # 音は1つで数 MB あり、聴き直すたびに重ねて送ると1回の送信が際限なく太るため
    # （先に聴いた箇所は「聴いた」の一文になる。音そのものは最後の箇所で耳に届いている）。
    last_live: dict[str, int] = {}
    if live_turn:
        for p in (p for m in messages if isinstance(m.get("content"), list) for p in m["content"]):
            if isinstance(p, dict) and p.get("type") == AUDIO_REF_TYPE and p.get("turn") == live_turn:
                last_live[p.get("path", "")] = id(p)
    out = None
    for i, m in enumerate(messages):
        c = m.get("content")
        if not isinstance(c, list) or not any(
                isinstance(p, dict) and p.get("type") == AUDIO_REF_TYPE for p in c):
            continue
        parts = []
        for p in c:
            if not (isinstance(p, dict) and p.get("type") == AUDIO_REF_TYPE):
                parts.append(p)
                continue
            data = None
            if live_turn and p.get("turn") == live_turn and last_live.get(p.get("path", "")) == id(p):
                data = _load_audio_data(workspace_path, p.get("path", ""), p.get("seconds") or 0)
            if data:
                parts.append({"type": "input_audio",
                              "input_audio": {"data": data, "format": p.get("format") or "mp3"}})
            elif (live_turn and p.get("turn") == live_turn and not p.get("heard")
                  and last_live.get(p.get("path", "")) not in (None, id(p))):
                # 同じターンに同じ音をこのあとでもう一度渡している。音そのものは後ろの1か所に載る
                parts.append({"type": "text", "text": t("ear_relisten_placeholder", path=p.get("path", ""))})
            else:
                parts.append({"type": "text", "text": placeholder_text(p)})
        if out is None:
            out = list(messages)
        nm = dict(m)
        # 一文だけになったら文字列に畳む（リスト形式の content を受け付けない LLM への配慮）
        if all(isinstance(p, dict) and p.get("type") == "text" for p in parts):
            nm["content"] = "\n".join(p.get("text", "") for p in parts)
        else:
            nm["content"] = parts
        out[i] = nm
    return out if out is not None else messages
