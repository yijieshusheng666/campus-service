"""语音转写（ASR）：服务层单元测试 + 端点校验。

网络一律 mock（不真调智谱），覆盖：
1. 热词抽取（白名单命中、上限、空输入）
2. multipart 字段构造——**尤其 data 必须是 dict**（踩过的坑，见 _build_fields 注释）
3. 响应解析兼容两种结构
4. 服务层校验：空音频 / 超限 / 缺 API Key
5. 降级路径：带热词被 4xx 拒绝 → 去掉热词重试成功
6. 重试上限：连续 429 → 最终抛 ASRError
7. 端点：鉴权、面试存在性、音频格式校验、成功返回
"""
import json
import re

import pytest

from app.config import settings
from app.services import asr as asr_mod
from app.services.asr import (
    ASRError,
    _build_fields,
    _extract_text,
    extract_hotwords,
    transcribe,
)

# 最小合法 WAV 头（仅用于格式判断，不是可播放文件）
WAV_HEADER = b"RIFF" + b"\x00" * 4 + b"WAVEfmt "


class _Resp:
    """伪造 httpx.Response 的最小接口。"""

    def __init__(self, status_code: int = 200, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = b"{}"
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _fast_and_authed(monkeypatch):
    """补上 API Key 并把退避间隔清零（否则重试用例会真的 sleep 数秒）。"""
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(asr_mod, "_BACKOFF", (0, 0))


# ---- 热词抽取 ----


def test_extract_hotwords_hits_resume_terms():
    words = extract_hotwords("熟悉 FastAPI 与 WebSocket，做过幂等改造和 SSE 流式输出")
    assert "FastAPI" in words
    assert "WebSocket" in words
    assert "SSE" in words
    assert "幂等" in words


def test_extract_hotwords_empty_and_plain_text():
    assert extract_hotwords("") == []
    assert extract_hotwords("这是一段没有任何技术名词的普通文字") == []


def test_extract_hotwords_respects_limit():
    full = " ".join(asr_mod.TECH_HOTWORDS)
    assert len(extract_hotwords(full, limit=5)) == 5
    assert len(extract_hotwords(full)) == len(asr_mod.TECH_HOTWORDS)  # 全命中时等于白名单长度


# ---- multipart 字段构造 ----


def test_build_fields_returns_mapping_and_json_hotwords():
    """回归测试：data 必须是 Mapping。

    httpx 只在 data 是 Mapping 时才走 multipart 编码；传 list of tuples 会被当成
    原始请求体并生成同步流，在 AsyncClient 上抛
    「Attempted to send an sync request with an AsyncClient instance.」。
    """
    fields = _build_fields("上一段转写", ["FastAPI", "SSE"])
    assert isinstance(fields, dict)
    assert fields["model"] == settings.ASR_MODEL
    assert fields["stream"] == "false"
    assert json.loads(fields["hotwords"]) == ["FastAPI", "SSE"]


def test_build_fields_trims_prompt_and_omits_empty_hotwords():
    fields = _build_fields("x" * 5000, None)
    assert len(fields["prompt"]) == 2000          # 只保留尾部
    assert "hotwords" not in fields
    assert "prompt" not in _build_fields("", None)


# ---- 响应解析 ----


def test_extract_text_supports_both_shapes():
    assert _extract_text({"text": "  你好  "}) == "你好"
    assert _extract_text({"choices": [{"message": {"content": "hello"}}]}) == "hello"
    assert _extract_text({}) == ""
    assert _extract_text("not-a-dict") == ""
    assert _extract_text({"text": None}) == ""


# ---- 服务层校验 ----


async def test_transcribe_rejects_empty_audio():
    with pytest.raises(ASRError):
        await transcribe(b"")


async def test_transcribe_rejects_oversize_audio(monkeypatch):
    monkeypatch.setattr(settings, "ASR_MAX_BYTES", 10)
    with pytest.raises(ASRError) as e:
        await transcribe(b"x" * 20)
    assert "MB" in str(e.value)


async def test_transcribe_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    with pytest.raises(ASRError) as e:
        await transcribe(WAV_HEADER)
    assert "LLM_API_KEY" in str(e.value)


# ---- 成功与降级 ----


async def test_transcribe_success_strips_whitespace(monkeypatch):
    async def fake_post(url, api_key, audio, filename, fields):
        assert url.endswith("/audio/transcriptions")
        assert api_key == "test-key"
        return _Resp(200, {"text": " 我熟悉 FastAPI "})

    monkeypatch.setattr(asr_mod, "_post_once", fake_post)
    assert await transcribe(WAV_HEADER) == "我熟悉 FastAPI"


async def test_transcribe_drops_hotwords_when_rejected(monkeypatch):
    """热词是增强项：上游不认这个参数时必须降级，而不是让整次转写失败。"""
    seen = []

    async def fake_post(url, api_key, audio, filename, fields):
        seen.append("hotwords" in fields)
        if "hotwords" in fields:
            return _Resp(400, text="invalid hotwords")
        return _Resp(200, {"text": "成功"})

    monkeypatch.setattr(asr_mod, "_post_once", fake_post)
    text = await transcribe(WAV_HEADER, hotwords=["FastAPI"])
    assert text == "成功"
    assert seen == [True, False]


async def test_transcribe_retries_then_raises_on_429(monkeypatch):
    calls = []

    async def fake_post(url, api_key, audio, filename, fields):
        calls.append(1)
        return _Resp(429, text="您的账户已达到速率限制")

    monkeypatch.setattr(asr_mod, "_post_once", fake_post)
    with pytest.raises(ASRError):
        await transcribe(WAV_HEADER)
    assert len(calls) == asr_mod._MAX_ATTEMPTS


async def test_transcribe_raises_immediately_on_4xx_without_hotwords(monkeypatch):
    """不带热词时的 4xx 是真实错误（如模型不存在），重试没有意义。"""
    calls = []

    async def fake_post(url, api_key, audio, filename, fields):
        calls.append(1)
        return _Resp(404, text="model not found")

    monkeypatch.setattr(asr_mod, "_post_once", fake_post)
    with pytest.raises(ASRError):
        await transcribe(WAV_HEADER)
    assert len(calls) == 1


# ---- 端点 ----


@pytest.fixture
def mock_stream(monkeypatch):
    """创建面试会走 SSE 首题，这里只替换提问，不触碰 LLM。"""
    async def _fake_stream(resume_text, job_position, history):
        yield "请先自我介绍。"

    monkeypatch.setattr("app.api.interviews.stream_question", _fake_stream)


async def _create_interview(auth_client) -> str:
    resp = await auth_client.post("/api/v1/interviews", json={"job_position": "后端开发"})
    assert resp.status_code == 201, resp.text
    return re.search(r'"interview_id":\s*(\d+)', resp.text).group(1)


async def test_transcribe_endpoint_requires_auth(client, mock_stream):
    resp = await client.post(
        "/api/v1/interviews/1/transcribe",
        files={"audio": ("a.wav", WAV_HEADER, "audio/wav")},
    )
    assert resp.status_code == 401


async def test_transcribe_endpoint_404_for_unknown_interview(auth_client, mock_stream):
    resp = await auth_client.post(
        "/api/v1/interviews/99999/transcribe",
        files={"audio": ("a.wav", WAV_HEADER, "audio/wav")},
    )
    assert resp.status_code == 404


async def test_transcribe_endpoint_rejects_non_wav(auth_client, mock_stream):
    iid = await _create_interview(auth_client)
    resp = await auth_client.post(
        f"/api/v1/interviews/{iid}/transcribe",
        files={"audio": ("a.webm", b"\x1aE\xdf\xa3webm-data", "audio/webm")},
    )
    assert resp.status_code == 400
    assert "WAV" in resp.json()["detail"]


async def test_transcribe_endpoint_empty_audio(auth_client, mock_stream):
    iid = await _create_interview(auth_client)
    resp = await auth_client.post(
        f"/api/v1/interviews/{iid}/transcribe",
        files={"audio": ("a.wav", b"", "audio/wav")},
    )
    assert resp.status_code == 400


async def test_transcribe_endpoint_ok_and_forwards_prompt(auth_client, mock_stream, monkeypatch):
    iid = await _create_interview(auth_client)
    captured = {}

    async def fake_transcribe(audio, filename="answer.wav", prompt="", hotwords=None):
        captured.update(audio=audio, filename=filename, prompt=prompt, hotwords=hotwords)
        return "我做过校园综合服务平台"

    monkeypatch.setattr("app.api.interviews.transcribe", fake_transcribe)
    resp = await auth_client.post(
        f"/api/v1/interviews/{iid}/transcribe",
        files={"audio": ("answer.wav", WAV_HEADER + b"\x00" * 64, "audio/wav")},
        data={"prompt": "上一段内容"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["text"] == "我做过校园综合服务平台"
    assert captured["prompt"] == "上一段内容"
    assert captured["audio"].startswith(b"RIFF")


async def test_transcribe_endpoint_502_on_asr_error(auth_client, mock_stream, monkeypatch):
    iid = await _create_interview(auth_client)

    async def fake_transcribe(*args, **kwargs):
        raise ASRError("语音识别失败（重试 3 次）")

    monkeypatch.setattr("app.api.interviews.transcribe", fake_transcribe)
    resp = await auth_client.post(
        f"/api/v1/interviews/{iid}/transcribe",
        files={"audio": ("answer.wav", WAV_HEADER + b"\x00" * 64, "audio/wav")},
    )
    assert resp.status_code == 502
