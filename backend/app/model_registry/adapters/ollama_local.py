"""Native Ollama HTTP adapter (/api/chat, /api/show) for text and page vision."""

from __future__ import annotations

import base64
import io
import json
import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..profiles import ModelProfile
from .openai_compatible import AdapterError, OpenAICompatibleAdapter, _count

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_MIN_NUM_CTX = 1_024
_MAX_NUM_CTX = 32_768
_DEFAULT_VISION_CTX = 8_192


def native_base_url(endpoint: str) -> str:
    """Derive the Ollama native origin from a validated Registry endpoint.

    Strips only an exact trailing ``/v1`` segment so endpoints never undergo
    arbitrary string substitution or unexpected path joins.
    """
    try:
        parsed = urlsplit(endpoint.strip())
    except ValueError as exc:
        raise AdapterError("AI_ENDPOINT_INVALID") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise AdapterError("AI_ENDPOINT_INVALID")
    path = parsed.path.rstrip("/")
    if path == "/v1":
        base_path = ""
    elif path == "":
        base_path = ""
    else:
        raise AdapterError("AI_ENDPOINT_INVALID")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, base_path, "", ""))


def _resolve_think(params: dict[str, Any]) -> bool | None:
    explicit = params.get("think")
    if isinstance(explicit, bool):
        return explicit
    if params.get("reasoning_effort") == "none":
        return False
    return None


def _resolve_format(params: dict[str, Any]) -> str | dict[str, Any] | None:
    response_format = params.get("response_format")
    if isinstance(response_format, dict):
        schema = response_format.get("schema")
        if isinstance(schema, dict):
            return schema
        json_schema = response_format.get("json_schema")
        if isinstance(json_schema, dict):
            nested = json_schema.get("schema")
            return nested if isinstance(nested, dict) else json_schema
        if response_format.get("type") == "json_object":
            return "json"
    if params.get("json_mode") is True:
        return "json"
    return None


def _bounded_num_ctx(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        ctx = int(value)
    except (TypeError, ValueError):
        return None
    if _MIN_NUM_CTX <= ctx <= _MAX_NUM_CTX:
        return ctx
    return None


def _extract_chat_content(decoded: Any) -> tuple[str, tuple[int | None, int | None]]:
    if not isinstance(decoded, dict):
        raise AdapterError("MODEL_RESPONSE_INVALID")
    usage = (
        _count(decoded.get("prompt_eval_count")),
        _count(decoded.get("eval_count")),
    )
    if decoded.get("done_reason") == "length" or decoded.get("done") is False:
        raise AdapterError("MODEL_OUTPUT_TRUNCATED")
    message = decoded.get("message")
    if not isinstance(message, dict):
        raise AdapterError("MODEL_RESPONSE_INVALID")
    content = message.get("content")
    if not isinstance(content, str):
        raise AdapterError("MODEL_RESPONSE_INVALID")
    # Reasoning-only or empty message.content must never count as a usable answer.
    if not _THINK_BLOCK.sub("", content).strip():
        raise AdapterError("MODEL_EMPTY_ANSWER")
    return content, usage


class OllamaLocalAdapter(OpenAICompatibleAdapter):
    """Native Ollama adapter using ``/api/chat`` and ``/api/show``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.last_model_digest: str | None = None

    async def generate(
        self,
        messages: Sequence[dict[str, str]],
        profile: ModelProfile,
        *,
        stream: bool = False,
    ) -> str:
        if stream:
            raise AdapterError("STREAM_UNSUPPORTED")
        if not messages:
            raise AdapterError("MODEL_REQUEST_INVALID")

        params = profile.params if isinstance(profile.params, dict) else {}
        options: dict[str, Any] = {
            "num_predict": self._bounded_tokens(params.get("max_tokens")),
        }
        for name in ("temperature", "top_p"):
            value = params.get(name)
            if isinstance(value, int | float) and not isinstance(value, bool):
                options[name] = value
        num_ctx = _bounded_num_ctx(params.get("num_ctx"))
        if num_ctx is not None:
            options["num_ctx"] = num_ctx

        payload: dict[str, Any] = {
            "model": profile.model_id,
            "messages": [dict(item) for item in messages],
            "stream": False,
            "options": options,
        }
        think = _resolve_think(params)
        if think is not None:
            payload["think"] = think
        fmt = _resolve_format(params)
        if fmt is not None:
            payload["format"] = fmt

        base = native_base_url(profile.endpoint)
        data = await self._request(
            "POST",
            f"{base}/api/chat",
            headers=self._headers(),
            json_body=payload,
        )
        try:
            decoded = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise AdapterError("MODEL_RESPONSE_INVALID") from exc
        content, usage = _extract_chat_content(decoded)
        self.last_usage = usage
        return content

    async def generate_vision(
        self,
        *,
        image_png: bytes,
        prompt: str,
        schema: dict[str, Any],
        profile: ModelProfile,
    ) -> str:
        """Send one backend-rendered PNG image to Ollama native ``/api/chat``."""
        if (
            not image_png
            or len(image_png) > _MAX_IMAGE_BYTES
            or not image_png.startswith(_PNG_MAGIC)
        ):
            raise AdapterError("MODEL_REQUEST_INVALID")
        if not prompt.strip() or not isinstance(schema, dict):
            raise AdapterError("MODEL_REQUEST_INVALID")

        params = profile.params if isinstance(profile.params, dict) else {}
        num_ctx = _bounded_num_ctx(params.get("num_ctx")) or _DEFAULT_VISION_CTX
        temperature = params.get("temperature")
        if not isinstance(temperature, int | float) or isinstance(temperature, bool):
            temperature = 0
        think = params.get("think")
        think_flag = think if isinstance(think, bool) else False

        options: dict[str, Any] = {
            "num_predict": self.max_tokens,
            "num_ctx": num_ctx,
            "temperature": temperature,
        }
        top_p = params.get("top_p")
        if isinstance(top_p, int | float) and not isinstance(top_p, bool):
            options["top_p"] = top_p

        b64_image = base64.b64encode(image_png).decode("ascii")
        payload: dict[str, Any] = {
            "model": profile.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64_image],
                }
            ],
            "stream": False,
            "think": think_flag,
            "format": schema,
            "options": options,
        }

        base = native_base_url(profile.endpoint)
        data = await self._request(
            "POST",
            f"{base}/api/chat",
            headers=self._headers(),
            json_body=payload,
        )
        try:
            decoded = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise AdapterError("MODEL_RESPONSE_INVALID") from exc
        content, usage = _extract_chat_content(decoded)
        self.last_usage = usage
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError) as exc:
            raise AdapterError("MODEL_RESPONSE_INVALID") from exc
        if not isinstance(parsed, dict):
            raise AdapterError("MODEL_RESPONSE_INVALID")
        return content

    async def show_model(self, profile: ModelProfile) -> dict[str, Any]:
        """Inspect ``POST /api/show`` to confirm capabilities and projector metadata."""
        base = native_base_url(profile.endpoint)
        data = await self._request(
            "POST",
            f"{base}/api/show",
            headers=self._headers(),
            json_body={"model": profile.model_id},
        )
        try:
            decoded = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise AdapterError("MODEL_RESPONSE_INVALID") from exc
        if not isinstance(decoded, dict):
            raise AdapterError("MODEL_RESPONSE_INVALID")
        digest = decoded.get("digest")
        if isinstance(digest, str) and digest:
            self.last_model_digest = digest
        elif self.supports_vision(decoded):
            # Ollama's /api/show normally omits the manifest digest. /api/tags is
            # the native endpoint that actually identifies the installed weights.
            self.last_model_digest = await self.model_digest(profile)
        return decoded

    async def model_digest(self, profile: ModelProfile) -> str:
        data = await self._request(
            "GET",
            f"{native_base_url(profile.endpoint)}/api/tags",
            headers=self._headers(),
            json_body=None,
        )
        try:
            decoded = json.loads(data)
        except (ValueError, TypeError) as exc:
            raise AdapterError("MODEL_RESPONSE_INVALID") from exc
        models = decoded.get("models") if isinstance(decoded, dict) else None
        if not isinstance(models, list):
            raise AdapterError("MODEL_RESPONSE_INVALID")
        requested = profile.model_id
        if ":" not in requested.rsplit("/", 1)[-1]:
            requested += ":latest"
        for model in models:
            if not isinstance(model, dict):
                continue
            name = model.get("name") or model.get("model")
            if isinstance(name, str) and ":" not in name.rsplit("/", 1)[-1]:
                name += ":latest"
            if name != requested:
                continue
            digest = str(model.get("digest", "")).removeprefix("sha256:")
            if re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                return "sha256:" + digest.lower()
            raise AdapterError("MODEL_RESPONSE_INVALID")
        raise AdapterError("MODEL_NOT_FOUND")

    @staticmethod
    def supports_vision(show_info: dict[str, Any]) -> bool:
        """Whether ``/api/show`` output demonstrates vision support."""
        capabilities = show_info.get("capabilities")
        if isinstance(capabilities, list) and "vision" in capabilities:
            return True
        if show_info.get("projector_info"):
            return True
        model_info = show_info.get("model_info")
        if isinstance(model_info, dict):
            for key in model_info:
                if "vision" in str(key).lower() or "projector" in str(key).lower():
                    return True
        return False


OCR_PROBE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}
OCR_PROBE_TEXT = "OCR-PROBE-17"


def valid_ocr_probe(content: str) -> bool:
    try:
        decoded = json.loads(content)
    except (TypeError, ValueError):
        return False
    value = decoded.get("text") if isinstance(decoded, dict) else None
    # This is a capability probe, not an OCR accuracy score. Keep the actual
    # letters/digits exact while allowing separator variation (e.g. OCR:PROBE-17).
    return isinstance(value, str) and re.sub(r"[-\s:]", "", value).upper() == "OCRPROBE17"


OCR_PROBE_PROMPT = (
    "Chép lại đúng chuỗi ký tự nhìn thấy trong ảnh kiểm tra này. "
    "Không thêm nhận xét; chỉ trả JSON theo schema."
)


def synthetic_ocr_probe_png(label: str = "OCR-PROBE-17") -> bytes:
    """Create a synthetic non-sensitive PNG image for vision readiness checks."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (320, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((24, 28), label, fill=(0, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
