# core/llm.py
"""
LLM API 抽象化レイヤー

役割:
    LLMプロバイダー（Deepseek, Claude, ローカル等）の違いを吸収し、
    統一的なインターフェースでLLMとの通信を提供する。

設計:
    - 全プロバイダーは LLMProvider 基底クラスを継承する
    - config.yaml の llm.provider でプロバイダーを切り替える
    - OpenAI互換APIを持つプロバイダーは OpenAICompatibleProvider で対応
      （Deepseek, ローカルLLM等はこれで動く）

拡張方法:
    新しいプロバイダーを追加する場合:
    1. LLMProvider を継承したクラスを作る
    2. create_provider() に分岐を追加する
"""

from core.time_utils import tlog
from core.i18n import t
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional
import json
import time
import yaml
from openai import AsyncOpenAI

# --- 簡体字検出（中国語混入防止） ---
# 日本語と同じ文字コードの字は入れないこと。「声」「将」が入っていたため、
# 声の話をするだけで簡体字と誤判定され、再生成が5回続いた（2026-09-12）。
_SIMPLIFIED_CHARS = set(
    "这个们说为时对过还么发经从动两长"
    "样现进实种话儿业间问电门东开头无"
    "让请认议论讲许诉该谁调谢谈识记设试读课"
    "钱错银钟铁针锁链镇钢"
    "红纪约纯纸线练组细织终绝绿继续编"
    "饭馆饮"
    "转较输轻辆软"
    "关闪闭闻阅闲"
    "妈骂驾骗验"
    "观规视觉览"
    "财货贵费贸购赛质贫败"
    "顺须预领题额颜"
    "鸡鹤"
    "你吗呢哪啊"
)

def _count_simplified(text: str) -> int:
    """テキスト中の簡体字の数を返す"""
    if not text:
        return 0
    return sum(1 for c in text if c in _SIMPLIFIED_CHARS)

# --- データ構造 ---

@dataclass
class ToolCall:
    """LLMが要求したツール呼び出し"""
    id: str           # ツール呼び出しのID（LLMが生成）
    name: str         # ツール名（例: "read_file"）
    arguments: dict   # 引数（例: {"path": "SOUL.md"}）


@dataclass 
class LLMResponse:
    """LLMからの応答"""
    content: Optional[str]           # テキスト応答（ツール呼び出し時はNone）
    tool_calls: list[ToolCall]       # ツール呼び出しリスト（テキスト応答時は空）
    raw: dict                        # 生のAPI応答（デバッグ用）
    reasoning_content: Optional[str] = None  # 追加


# --- 基底クラス ---

def parse_tool_arguments(raw: str, finish_reason=None) -> dict:
    """ツール引数の JSON 文字列を dict にする（chat / chat_streamed 共通）。

    壊れていた場合は {"__parse_error__", "raw_arguments", "__finish_reason__"} を返す。
    finish_reason が "length" なら max_tokens で出力が途中で打ち切られた（JSON が閉じる前に
    切れた）ケースで、柚月の書き方の問題ではない。agent 側はこれを見て文言を分ける。
    2026-09-03 に約8,000トークンの write_file が 4096 で切れ、「エスケープ漏れを確認」という
    誤った案内で柚月が長時間迷った事故があった。
    """
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError as e:
        if finish_reason == "length":
            tlog(f"[LLM] ツール引数が max_tokens で途中打ち切り（{len(raw)}文字）: {e}")
        else:
            tlog(f"[LLM] ツール引数の JSON パース失敗（finish_reason={finish_reason}）: {e}")
        return {"__parse_error__": str(e), "raw_arguments": raw, "__finish_reason__": finish_reason}


class LLMProvider(ABC):
    """全LLMプロバイダーが実装するインターフェース"""

    @abstractmethod
    async def chat(self, messages: list[dict], tools: Optional[list[dict]] = None) -> LLMResponse:
        """メッセージを送信し、応答を得る（非ストリーミング）"""
        pass

    async def chat_streamed(
        self, messages: list[dict], tools: Optional[list[dict]] = None,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        on_stream_reset: Optional[Callable[[], Awaitable[None]]] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        メッセージを送信し、テキスト断片を on_delta に流しながら完全な応答を返す。

        デフォルト実装はストリーミング非対応プロバイダ向けのフォールバック:
        chat() で完全な応答を得てから、完成テキストを1回だけ on_delta に渡す。
        戻り値の LLMResponse は chat() と完全に同形（呼び出し側は区別不要）。

        on_stream_reset は再生成（簡体字リトライ等）の開始時に呼ばれ、
        UI側が「ここまで流したテキストを破棄してやり直す」ために使う。
        """
        resp = await self.chat(messages, tools=tools, **kwargs)
        if on_delta and resp.content:
            await on_delta(resp.content)
        return resp


# --- モデル退避（フォールバック）サポート ---
# 実験モデル（例: ビジョン対応の *-vision-exp）が廃止・非対応になったとき、
# 従来モデルへ黙って落ちるのではなく「見えていない」ことを本人に伝えた上で退避する。
# レート制限や一時的な 5xx はここでは拾わない（再試行で回復しうるので従来通り上位へ投げる）。

_FALLBACK_COOLDOWN_SEC = 600  # 一度退避したら10分は最初から退避先で呼ぶ（毎回2回叩かないため）

# 実測で確認した文言を含める（推測だけで並べると肝心のときに退避が働かない）。
# 例: DeepSeek は廃止モデルに対し 400 で
#   "The supported API model names are ..., but you passed X." を返す（404 ではない）。
_MODEL_UNAVAILABLE_MARKERS = (
    "does not support image",     # 画像非対応モデルに画像を送った（実測）
    "supported api model names",  # モデル名が無効＝廃止・改名（DeepSeek 実測）
    "model not exist",            # 他プロバイダ向けの一般的な文言
    "model does not exist",
    "model_not_found",
    "unknown model",
)


def _is_model_unavailable_error(e: Exception) -> bool:
    """「そのモデルでは無理」系のエラーか（＝退避すべきか）を判定する。"""
    msg = str(e).lower()
    if getattr(e, "status_code", None) == 404:
        return True
    return any(m in msg for m in _MODEL_UNAVAILABLE_MARKERS)


def _strip_images_from_messages(messages: list[dict]) -> list[dict]:
    """メッセージから画像パートを外し、代わりに「見えていない」旨を本文に残す。

    画像は添付・see_image・ツール結果の3経路から入ってくるが、API に渡る直前の
    ここ1箇所で落とせば全経路をカバーできる。
    元のリスト（＝会話履歴そのもの）は決して書き換えない。履歴から画像が永久に
    消えてしまうのを避けるため、必ずコピーを返す。
    """
    stripped = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            stripped.append(msg)
            continue
        kept = [p for p in content
                if not (isinstance(p, dict) and p.get("type") == "image_url")]
        removed = len(content) - len(kept)
        if not removed:
            stripped.append(msg)
            continue
        kept.append({"type": "text", "text": t("llm_image_stripped_note", n=removed)})
        new_msg = dict(msg)
        new_msg["content"] = kept
        stripped.append(new_msg)
    return stripped


# --- API が画像を受け付けなかったとき ---
# 壊れた画像（途中で切れた PNG・中身が画像でない・SVG を PNG と名乗る等）は API が 400 で弾く。
# その画像が会話履歴に残ると、次の呼び出しでも同じ画像を送ってまた弾かれ、柚月の会話が止まり続ける。
# API はどの画像かを教えてくれるので、専用の例外にして番号を呼び出し側（core/agent.py）へ渡し、
# 履歴のその画像だけを差し替えて送り直せるようにする。
# 文言は 2026-09-12 に DeepSeek（deepseek-flash）で実測したもの。番号は system を含む messages の添字で、
# image[n] はそのメッセージ内の画像パートだけを数えた 0 始まりの番号:
#   ".messages[3].image[0]: You have uploaded an unsupported image. Please make sure your image is valid ..."
#   ".messages[3]: Invalid base64 data"（base64 自体が壊れているときは画像の番号が付かない）
# ストリーミングでも同じ 400（openai.BadRequestError）で返る。
_IMAGE_REJECTED_PATTERN = (
    r"\.messages\[(\d+)\](?:\.image\[(\d+)\])?:\s*"
    r"(?:You have uploaded an unsupported image|Invalid base64 data)"
)


class ImageRejectedError(Exception):
    """API が送った画像を受け付けなかった（壊れている・対応していない形式）。

    message_index: 送った messages の添字（system を含む）
    image_index:   そのメッセージ内で何枚目の画像か（画像パートだけを数えた 0 始まり）。分からなければ None
    original:      元の例外（直せなかったときは呼び出し側がこれを投げ直す）
    """

    def __init__(self, message_index: int, image_index: Optional[int], original: Exception):
        super().__init__(str(original))
        self.message_index = message_index
        self.image_index = image_index
        self.original = original


class ContextBudgetExceeded(Exception):
    """送ろうとした「入力＋出力の枠」が、モデルの窓（context_limit）に収まらない。

    API に送る前にこちらで数えて見つけた場合と、API が「長すぎる」と返した場合の両方で投げる。
    呼び出し側（柚月の会話）はこれを受けて生ターンを畳み、組み立て直して送り直す。
    DeepSeek V4.1 の窓は 1,048,576 で、判定は入力＋max_tokens（docs/CONTEXT_GUARD_DESIGN.md）。

    needed: 数えた「入力＋出力の枠」（API が返した場合は分からないので None）
    limit:  窓の大きさ（同上）
    """

    def __init__(self, needed: Optional[int], limit: Optional[int], original: Optional[Exception] = None):
        if needed is not None and limit is not None:
            msg = f"入力＋出力の枠 {needed:,} が窓 {limit:,} を超えています"
        else:
            msg = f"API がコンテキストの長さを受け付けませんでした: {original}"
        super().__init__(msg)
        self.needed = needed
        self.limit = limit
        self.original = original


# API が「窓に収まらない」と返したときの文面（OpenAI 互換の各社で共通の言い回し）。
# 例: "This model's maximum context length is 1048576 tokens. However, you requested ..."
_CONTEXT_EXCEEDED_PATTERN = r"maximum context length|context_length_exceeded|CONTEXT_WINDOW_EXCEEDED"


def _as_context_exceeded(e: Exception) -> Optional[ContextBudgetExceeded]:
    """「窓に収まらない」エラーなら ContextBudgetExceeded を返す。違えば None。"""
    import re
    if isinstance(e, ContextBudgetExceeded):
        return e
    if getattr(e, "status_code", 400) != 400:
        return None
    if not re.search(_CONTEXT_EXCEEDED_PATTERN, str(e), re.IGNORECASE):
        return None
    return ContextBudgetExceeded(None, None, e)


def _as_image_rejected(e: Exception) -> Optional[ImageRejectedError]:
    """「API が画像を受け付けなかった」エラーなら ImageRejectedError を返す。違えば None。"""
    import re
    if isinstance(e, ImageRejectedError):
        return e
    if getattr(e, "status_code", 400) != 400:
        return None
    m = re.search(_IMAGE_REJECTED_PATTERN, str(e))
    if not m:
        return None
    image_index = int(m.group(2)) if m.group(2) is not None else None
    return ImageRejectedError(int(m.group(1)), image_index, e)


# --- OpenAI互換プロバイダー ---

class OpenAICompatibleProvider(LLMProvider):
    """
    OpenAI互換APIを持つプロバイダー用の実装。
    Deepseek, ローカルLLM (Ollama/vLLM), OpenAI本体などに対応。
    base_url を変えるだけで切り替え可能。
    """
    
    def __init__(self, api_key: str, base_url: str, model: str,
                 temperature: float = 1.0, max_tokens: int = 4096,
                 provider: str = "", thinking: str = "auto",
                 fallback_model: str = ""):
        self.model = model
        # 実験モデルが使えなくなったときの退避先（空なら退避しない＝従来挙動）
        self.fallback_model = fallback_model or ""
        self._fallback_until = 0.0  # この時刻までは最初から退避先で呼ぶ
        self.provider = provider           # deepseek/openai/gemini/grok/local 等。thinking 適用の分岐に使う
        self.thinking = thinking or "auto" # auto/off/low/medium/high（thinking/reasoning モード）
        self.temperature = temperature
        self.max_tokens = max_tokens
        # モデルの窓（入力＋出力の合計の上限）を返す関数。None なら送る前に数えない。
        # 柚月の会話に使う llm には agent が context.max_tokens を返す関数を持たせる
        # （設定画面で上限を変えると、その場で関所も追従する）。
        # 別のモデルを積んだプロバイダ（Salia の 31B 等）は窓が違うので、ここでは決め打ちしない。
        self.context_limit_getter: Optional[Callable[[], int]] = None
        # このモデルの数え方でトークンを数える部品（count_text / count_messages を持つもの）。
        # None なら core/tokens.py（柚月の普段の LLM の数え方）で数える。
        # トークナイザーが違えば同じ文脈でも数が変わるので、別のモデルを積むプロバイダ
        # （耳＝core/ear.py）はここに自分の数え方を入れる。
        self.token_counter = None
        # AsyncOpenAI クライアントを初期化
        # base_url でAPI先を切り替える:
        #   Deepseek: https://api.deepseek.com
        #   Ollama:   http://localhost:11434/v1
        #   OpenAI:   https://api.openai.com/v1
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    
    def _build_chat_kwargs(self, messages: list[dict], tools: Optional[list[dict]],
                           frequency_penalty_override: Optional[float],
                           temperature_override: Optional[float] = None) -> dict:
        """chat / chat_streamed 共通の API リクエスト引数を構築する

        temperature_override は「この1回だけ」温度を差し替える（会話用の self.temperature は
        触らない）。会話要約（summary_v2）は採点順位の再現性のため 0.2 で回す設計だが、
        self.temperature を書き換えると同時に走っている柚月の会話にも効いてしまうため、
        呼び出し単位で渡す。
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature_override is None else temperature_override,
            "max_tokens": self.max_tokens,
        }
        if not self.model.startswith("gemini"):
            kwargs["frequency_penalty"] = frequency_penalty_override if frequency_penalty_override is not None else 0.5
        # thinking（reasoning）モードを設定値 self.thinking から provider 別に適用する。
        # 以前はモデル名（flash/pro）から推測していたが、同一モデルで thinking を切り替えられず、
        # サリアと本体で別々に設定もできなかったため、明示設定（auto/off/low/medium/high）に変更した。
        # auto は何も足さない（モデル既定に任せる）。
        apply_thinking(kwargs, self.provider, self.model, self.thinking)

        # ツール定義がある場合のみ渡す
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"  # LLMが自分で判断
        return kwargs

    def _fallback_kwargs(self, kwargs: dict) -> dict:
        """退避先モデル用の kwargs を作る（モデル差し替え＋画像除去）。"""
        fb = dict(kwargs)
        fb["model"] = self.fallback_model
        fb["messages"] = _strip_images_from_messages(kwargs.get("messages") or [])
        return fb

    def _check_context_budget(self, kwargs: dict) -> None:
        """送る前に「入力＋出力の枠」を数え、窓に収まらなければ ContextBudgetExceeded を投げる。

        判定をここ（すべての呼び出しが通る送信口）に置くのは、会話側の判定をどこに置いても
        「積んでから送るまで」の隙間が残るため（2026-09-19 カノン「入力を API に与える前に
        トークン数チェックを入れるべき・いかなる場合でも」）。
        数え方は core/tokens.py（API の実測との差は約0.3%）。数えた結果は文字列ごとに
        覚えてあるので、全体を数えても1回0.1秒程度。
        """
        getter = self.context_limit_getter
        if getter is None:
            return
        try:
            limit = int(getter() or 0)
        except Exception:
            return
        if limit <= 0:
            return
        import json as _json
        counter = getattr(self, "token_counter", None)
        if counter is not None:
            count_messages_tokens, count_text_tokens = counter.count_messages, counter.count_text
        else:
            from core.tokens import count_messages_tokens, count_text_tokens
        needed = count_messages_tokens(kwargs.get("messages") or [])
        if kwargs.get("tools"):
            needed += count_text_tokens(_json.dumps(kwargs["tools"], ensure_ascii=False))
        needed += int(kwargs.get("max_tokens") or 0)
        if needed > limit:
            tlog(f"[LLM] 入力＋出力の枠 {needed:,} が窓 {limit:,} を超えるため送りません")
            raise ContextBudgetExceeded(needed, limit)

    async def _create(self, **kwargs):
        """API 呼び出し本体。

        送る前に窓に収まるかを数える（_check_context_budget）。収まらなければ送らずに
        ContextBudgetExceeded を投げ、API が「長すぎる」と返したときも同じ例外に包む。
        API が画像を受け付けなかった（壊れている・形式が違う）ときは ImageRejectedError に包んで投げる。
        どの画像かの番号を持たせて、呼び出し側が履歴のその画像だけを直して送り直せるようにするため
        （退避先モデルへ逃げても、画像を全部落とすことになり柚月には何も見えなくなる）。
        """
        self._check_context_budget(kwargs)
        try:
            return await self._create_with_fallback(**kwargs)
        except Exception as e:
            exceeded = _as_context_exceeded(e)
            if exceeded is not None and exceeded is not e:
                raise exceeded from e
            rejected = _as_image_rejected(e)
            if rejected is not None and rejected is not e:
                raise rejected from e
            raise

    async def _create_with_fallback(self, **kwargs):
        """モデルが使えないときだけ退避先モデルで再送する。

        退避先は画像を見られない前提なので、画像は落とし「見えていない」旨を本文に残す。
        こうしないと、見えていない画像について本人が語り出してしまう。
        """
        if not self.fallback_model or self.fallback_model == self.model:
            return await self.client.chat.completions.create(**kwargs)

        # 直近で退避したばかりなら、最初から退避先で呼ぶ（毎回2回叩いて遅くならないため）
        if time.monotonic() < self._fallback_until:
            return await self.client.chat.completions.create(**self._fallback_kwargs(kwargs))

        try:
            return await self.client.chat.completions.create(**kwargs)
        except Exception as e:
            if not _is_model_unavailable_error(e):
                raise  # レート制限・一時障害等は従来通り上位へ
            self._fallback_until = time.monotonic() + _FALLBACK_COOLDOWN_SEC
            tlog(f"[LLM] {self.model} が使えないため {self.fallback_model} へ退避します"
                 f"（画像は送りません・{_FALLBACK_COOLDOWN_SEC}秒間）: {e}")
            return await self.client.chat.completions.create(**self._fallback_kwargs(kwargs))

    def _log_reasoning(self, rc: str) -> None:
        """reasoning_content（thinking時の中間思考）をログファイルに書き出す"""
        try:
            from datetime import datetime
            with open("logs/reasoning.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\t{rc}\n")
        except Exception:
            pass

    def _log_usage(self, u) -> None:
        """トークン使用量をコンソールとログファイルに記録する"""
        cached = getattr(u, 'prompt_tokens_details', None)
        cached_count = getattr(cached, 'cached_tokens', 0) if cached else 0
        # コンソールはキャッシュのミス／ヒット／出力の3つで見せる（in と total は読み取りにくいので出さない）
        miss_count = max((u.prompt_tokens or 0) - (cached_count or 0), 0)
        tlog(f"[LLM] tokens: ミス={miss_count:,} ヒット={cached_count or 0:,} 出力={u.completion_tokens or 0:,}")
        try:
            from datetime import datetime
            with open("logs/llm_usage.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\tin={u.prompt_tokens}\tcached={cached_count}\tout={u.completion_tokens}\ttotal={u.total_tokens}\n")
        except Exception:
            pass

    async def chat(self, messages: list[dict], tools: Optional[list[dict]] = None,
                   frequency_penalty_override: Optional[float] = None,
                   temperature_override: Optional[float] = None) -> LLMResponse:
        """
        LLMにメッセージを送信し、完全な応答を得る。
        ツール呼び出しが含まれる場合は tool_calls に格納される。
        """
        kwargs = self._build_chat_kwargs(messages, tools, frequency_penalty_override,
                                         temperature_override)

        max_chinese_retry = 5
        for attempt in range(max_chinese_retry + 1):
            response = await self._create(**kwargs)
            if response is None:
                continue
            # reasoning_contentをログに書き出す
            rc = getattr(response.choices[0].message, 'reasoning_content', None)
            if rc:
                self._log_reasoning(rc)
            if hasattr(response, 'usage') and response.usage:
                self._log_usage(response.usage)
            choice = response.choices[0].message

            # 簡体字チェック（テキスト応答 + ツール引数の両方）
            check_text = choice.content or ""
            if choice.tool_calls:
                for tc in choice.tool_calls:
                    try:
                        check_text += " " + tc.function.arguments
                    except Exception:
                        pass
            sc_count = _count_simplified(check_text)
            if sc_count >= 5 and attempt < max_chinese_retry:
                tlog(f"[LLM] 簡体字検出 ({sc_count}文字, 試行{attempt+1}/{max_chinese_retry}) → 再生成")
                # 再生成時にシステムメッセージを追加
                # content は画像つきならリスト、ツール呼び出しなら None になる。文字列のときだけ見る
                # （見ずに startswith すると再生成せずにターンごと落ちていた。9/6・9/12 に発生）
                if not any(isinstance(m.get("content"), str)
                           and m["content"].startswith("[SYSTEM] 日本語で") for m in messages):
                    messages.append({
                        "role": "user",
                        "content": "[SYSTEM] 日本語で回答してください。中国語（簡体字）は使用禁止です。"
                    })
                continue
            if sc_count >= 5:
                tlog(f"[LLM] 簡体字検出 ({sc_count}文字) → {max_chinese_retry}回再生成しても解消せず")
            break

        # ツール呼び出しの解析（finish_reason="length" は max_tokens 打ち切り）
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        tool_calls = []
        if choice.tool_calls:
            for tc in choice.tool_calls:
                args = parse_tool_arguments(tc.function.arguments, finish_reason)
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        return LLMResponse(
            content=choice.content,
            tool_calls=tool_calls,
            raw=response.model_dump(),
            reasoning_content=getattr(choice, 'reasoning_content', None),  # 追加
        )
        
    async def chat_streamed(
        self, messages: list[dict], tools: Optional[list[dict]] = None,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        on_stream_reset: Optional[Callable[[], Awaitable[None]]] = None,
        frequency_penalty_override: Optional[float] = None,
    ) -> LLMResponse:
        """
        LLMにメッセージを送信し、テキスト断片を on_delta に流しながら完全な応答を返す。
        戻り値は chat() と完全に同形の LLMResponse（ツール呼び出し・usage含む）。
        ストリーム開始に失敗した場合は chat() に自動フォールバックする。
        """
        kwargs = self._build_chat_kwargs(messages, tools, frequency_penalty_override)
        kwargs["stream"] = True
        # usage はストリーム最終チャンクで受け取る（スタミナ計算・トークンバーに必要）
        kwargs["stream_options"] = {"include_usage": True}

        max_chinese_retry = 5
        for attempt in range(max_chinese_retry + 1):
            try:
                stream = await self._create(**kwargs)
            except (ImageRejectedError, ContextBudgetExceeded):
                # 送り方（stream_options の有無・非ストリーミング）を変えても同じ画像で弾かれるので、
                # 叩き直さずに呼び出し側（履歴の画像を直して送り直す）へ渡す。
                # 窓に収まらないのも送り方では直らないので同じ（呼び出し側が畳んで送り直す）
                raise
            except Exception as e:
                if "stream_options" in kwargs:
                    # gemini互換等、stream_options 非対応エンドポイントの可能性 → 外して1回だけ再試行
                    tlog(f"[LLM] stream_options を外して再試行: {e}")
                    kwargs.pop("stream_options", None)
                    try:
                        stream = await self._create(**kwargs)
                    except (ImageRejectedError, ContextBudgetExceeded):
                        raise  # 外側と同じく、叩き直さずに呼び出し側へ
                    except Exception as e2:
                        tlog(f"[LLM] ストリーム開始失敗、非ストリーミングへフォールバック: {e2}")
                        return await self.chat(messages, tools=tools, frequency_penalty_override=frequency_penalty_override)
                else:
                    tlog(f"[LLM] ストリーム開始失敗、非ストリーミングへフォールバック: {e}")
                    return await self.chat(messages, tools=tools, frequency_penalty_override=frequency_penalty_override)

            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_acc: dict[int, dict] = {}  # index → {"id","name","args"}（部分JSONを連結して組み立てる）
            usage = None
            # 終了理由（"stop" / "tool_calls" / "length" など）。終端チャンクの choice に載る。
            # 簡体字再生成でやり直す際に前の試行の値が残らないよう、試行ごとに初期化する。
            finish_reason = None
            try:
                async for chunk in stream:
                    # usage は choices が空の最終チャンクに載ってくる
                    if getattr(chunk, "usage", None):
                        usage = chunk.usage
                    if not chunk.choices:
                        continue
                    fr = getattr(chunk.choices[0], "finish_reason", None)
                    if fr:
                        finish_reason = fr
                    delta = chunk.choices[0].delta
                    if delta is None:
                        continue
                    rc = getattr(delta, "reasoning_content", None)
                    if rc:
                        reasoning_parts.append(rc)
                    if delta.content:
                        content_parts.append(delta.content)
                        if on_delta:
                            await on_delta(delta.content)
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            acc = tool_acc.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                            if tc.id:
                                acc["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    acc["name"] += tc.function.name
                                if tc.function.arguments:
                                    acc["args"] += tc.function.arguments
            finally:
                # 中断（CancelledError）や途中エラーでもHTTP接続を確実に閉じる
                try:
                    await stream.close()
                except Exception:
                    pass

            content = "".join(content_parts)
            reasoning = "".join(reasoning_parts) or None
            if reasoning:
                self._log_reasoning(reasoning)
            if usage:
                self._log_usage(usage)

            # 簡体字チェック（chat() と同じ基準: テキスト応答 + ツール引数）
            check_text = content
            for acc in tool_acc.values():
                check_text += " " + acc["args"]
            sc_count = _count_simplified(check_text)
            if sc_count >= 5 and attempt < max_chinese_retry:
                tlog(f"[LLM] 簡体字検出 ({sc_count}文字, 試行{attempt+1}/{max_chinese_retry}) → 再生成")
                # content は画像つきならリスト、ツール呼び出しなら None になる。文字列のときだけ見る
                # （見ずに startswith すると再生成せずにターンごと落ちていた。9/6・9/12 に発生）
                if not any(isinstance(m.get("content"), str)
                           and m["content"].startswith("[SYSTEM] 日本語で") for m in messages):
                    messages.append({
                        "role": "user",
                        "content": "[SYSTEM] 日本語で回答してください。中国語（簡体字）は使用禁止です。"
                    })
                # UI側に「ここまでのストリームを破棄してやり直す」ことを通知
                if on_stream_reset:
                    await on_stream_reset()
                continue
            if sc_count >= 5:
                tlog(f"[LLM] 簡体字検出 ({sc_count}文字) → {max_chinese_retry}回再生成しても解消せず")
            break

        # ツール呼び出しの解析（chat() と同じパースエラー処理）
        tool_calls = []
        for idx in sorted(tool_acc):
            acc = tool_acc[idx]
            args = parse_tool_arguments(acc["args"], finish_reason)
            tool_calls.append(ToolCall(id=acc["id"], name=acc["name"], arguments=args))

        # raw は agent 側が usage しか読まないため、ストリームでは最小限の dict を組み立てる
        raw = {
            "usage": usage.model_dump() if usage else {},
            "streamed": True,
            "model": self.model,
        }
        return LLMResponse(
            content=content or None,
            tool_calls=tool_calls,
            raw=raw,
            reasoning_content=reasoning,
        )


# --- Claudeプロバイダー（将来用のスケルトン） ---

class ClaudeProvider(LLMProvider):
    """
    Anthropic Claude API用のプロバイダー。
    Claude APIはOpenAI互換ではないため、個別実装が必要。
    
    TODO: 必要になった時点で実装する
    """
    
    def __init__(self, api_key: str, model: str = "claude-opus-4-6", **kwargs):
        self.api_key = api_key
        self.model = model
        # anthropic パッケージが必要
        # pip install anthropic
    
    async def chat(self, messages, tools=None, **kwargs) -> LLMResponse:
        raise NotImplementedError("Claude provider is not yet implemented")


# --- 未設定プロバイダ（配布版の初期状態用） ---

class UnconfiguredProvider(LLMProvider):
    """LLM プロバイダが未選択のとき使うダミープロバイダ。

    配布版は config.yaml の provider を空にして出荷し、ユーザーが初回に
    「設定 → LLM設定」で好きなプロバイダ（deepseek / claude / openai / local 等）を
    選ぶ方式。プロバイダ未選択のまま会話されたら、deepseek 等を勝手に仮定せず、
    設定方法を案内するメッセージを返す（実APIは叩かない）。
    dev は config.yaml に provider があるためここは使われない。
    """

    SETUP_MESSAGE = (
        "まだ使う AI（LLMプロバイダ）が選ばれていません。\n\n"
        "画面上部の「設定」→「LLM設定」を開いて、使いたいプロバイダ"
        "（deepseek / claude / openai / ローカル 等）とモデルを選んでください。\n"
        "次に「APIキー管理」で、そのプロバイダの API キーを登録します。\n"
        "最後に画面右上の「再起動」ボタンを押すと反映されます。\n\n"
        "設定が終わったら、もう一度話しかけてくださいね。"
    )

    def __init__(self):
        # update_llm_config が稼働中プロバイダに temperature/max_tokens を代入するため属性を持たせる
        self.temperature = 1.0
        self.max_tokens = 4096

    async def chat(self, messages: list[dict], tools: Optional[list[dict]] = None, **kwargs) -> LLMResponse:
        return LLMResponse(content=self.SETUP_MESSAGE, tool_calls=[], raw={"unconfigured": True})


# --- thinking（reasoning）モードの provider 別適用 ---

def apply_thinking(kwargs: dict, provider: str, model: str, level: str) -> None:
    """統一 thinking 設定（auto/off/low/medium/high）を、OpenAI互換プロバイダの
    API パラメータに変換して kwargs に適用する（in-place）。

    各社仕様（2026・docs/LLM_THINKING_DESIGN.md 参照）:
      - DeepSeek V4 : extra_body={"thinking":{"type":"enabled"/"disabled"}} ＋ reasoning_effort(high/max)
                      ※low/medium は high に丸まる。off は thinking disabled（reasoning_effort 不可）
      - OpenAI/Gemini/Grok/Qwen : reasoning_effort = none/low/medium/high
                      ※Qwen3.8 は既定が思考あり。none で思考オフ（2026-09-20 QwenCloud で実測）
      - local/lmstudio/ollama/custom : 能力不明のため auto 以外は送らない（誤パラメータでの error 回避）
    auto は何も足さない（モデル既定）。
    """
    lvl = (level or "auto").lower()
    if lvl == "auto":
        return
    p = (provider or "").lower()
    m = (model or "").lower()

    is_deepseek = p == "deepseek" or "deepseek" in m
    # qwen はプロバイダ名が qwen のときだけ（モデル名では見ない。Ollama 等のローカルで
    # qwen 系を動かしている人に、対応の読めない引数を送らないため）
    is_effort = (p in ("openai", "gemini", "grok", "qwen")
                 or m.startswith(("gpt", "o1", "o3", "o4", "gemini", "grok")))

    if is_deepseek:
        eb = dict(kwargs.get("extra_body") or {})
        if lvl == "off":
            eb["thinking"] = {"type": "disabled"}
            kwargs.pop("reasoning_effort", None)  # disabled時は reasoning_effort 不可
        else:
            eb["thinking"] = {"type": "enabled"}
            # DeepSeek は high/max のみ。low/medium/high → high、（必要なら最大は max）
            kwargs["reasoning_effort"] = "high"
        kwargs["extra_body"] = eb
    elif is_effort:
        # OpenAI/Gemini/Grok は reasoning_effort をそのまま。off は none。
        kwargs["reasoning_effort"] = "none" if lvl == "off" else lvl
    else:
        # local/lmstudio/ollama/custom 等は対応が読めないので何も送らない（auto と同等）。
        return


# --- ファクトリー関数 ---

def create_provider(config: dict) -> LLMProvider:
    """
    config.yaml の設定からLLMプロバイダーを生成する。
    
    使い方:
        from core.config_loader import load_config
        config = load_config()
        provider = create_provider(config["llm"])
    
    新しいプロバイダーを追加する場合:
        1. LLMProvider を継承したクラスを作る
        2. ここに elif 分岐を追加する
    """
    import os
    import re

    # provider 未設定（配布版の初期状態）。deepseek 等を勝手に仮定せず、ユーザーに
    # 「設定→LLM設定でプロバイダを選んでください」と案内する未設定プロバイダを返す。
    # dev は config.yaml に provider:"deepseek" があるためここには来ない（挙動不変）。
    provider_name = config.get("provider")
    if not provider_name:
        print("[LLM] provider 未設定。UnconfiguredProvider（設定案内）を使用します。")
        return UnconfiguredProvider()
    
    # APIキーの取得ロジック（環境変数の動的解決を含む）
    api_key_raw = config.get("api_key", "")
    api_key = ""
    
    if api_key_raw:
        # "${CG_LLM_XXX_API_KEY}" のような形式かチェック
        match = re.match(r'^\$\{([A-Za-z0-9_]+)\}$', str(api_key_raw).strip())
        if match:
            env_var_name = match.group(1)
            api_key = os.environ.get(env_var_name, "")
        else:
            api_key = api_key_raw
    
    if not api_key:
        # まず UI（APIキー管理）から登録される CG_LLM_XXX_API_KEY を探索
        api_key = os.environ.get(f"CG_LLM_{provider_name.upper()}_API_KEY", "")
        # なければ従来の XXX_API_KEY をフォールバックとして探索
        if not api_key:
            api_key = os.environ.get(f"{provider_name.upper()}_API_KEY", "")

    # 健全化: 過去バグで config.yaml が api_key: \"${VAR}\" に壊れていると、確定キーが
    # \"sk-...\" のように前後にダブルクォート/バックスラッシュを含むことがある。APIキーに
    # これらは含まれないため、前後の空白・"・\ を除去して過去破損データも救済する。
    # （"・\ を1つの文字集合で strip しないと \"key\" の先頭 " が残るため注意）
    if api_key:
        api_key = api_key.strip().strip('"\\')

    if provider_name in ("deepseek", "openai", "local", "lmstudio", "ollama", "custom", "gemini", "grok", "anthropic"):
        # Anthropic, Gemini等は暫定的にOpenAI互換を試みるか、独自のAPI呼び出しクラスを作る必要があります。
        # ここでは指示に従い、まず全ての設定をパース・ルーティングできるようにします。
        default_urls = {
            "deepseek": "https://api.deepseek.com",
            "openai": "https://api.openai.com/v1",
            "local": "http://localhost:11434/v1",
            "lmstudio": "http://127.0.0.1:1234/v1",
            "ollama": "http://127.0.0.1:11434/v1",
            "custom": "",
            "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "grok": "https://api.x.ai/v1"
        }
        
        if provider_name == "claude" or provider_name == "anthropic":
            return ClaudeProvider(
                api_key=api_key,
                model=config.get("model", "claude-opus-4-6"),
            )
            
        base_url = config.get("base_url", default_urls.get(provider_name, ""))
        
        # model 欠落時もクラッシュさせない（キーがある時は従来通り）。
        model_name = config.get("model")
        if not model_name:
            print("警告: llm 設定に 'model' がありません。'deepseek-chat' で続行します。")
            model_name = "deepseek-chat"

        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=config.get("temperature", 1.0),
            max_tokens=config.get("max_tokens", 4096),
            provider=provider_name,
            thinking=config.get("thinking", "auto"),
            fallback_model=config.get("fallback_model", ""),
        )
    

    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")# core/__init__.py
# このディレクトリはエージェントの中核モジュールです