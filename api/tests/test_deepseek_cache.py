"""Round 22：DeepSeek prefix cache 观测（stream_options + cache usage 提取）。"""

from app.services.agent_traces import extract_cache_usage, extract_usage
from app.services.deepseek_client import DeepSeekClient


def test_stream_payload_enables_include_usage() -> None:
    payload = DeepSeekClient._build_payload(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        json_mode=True,
        thinking="enabled",
        reasoning_effort="high",
        temperature=0.7,
        max_tokens=None,
    )
    assert payload["stream_options"] == {"include_usage": True}


def test_non_stream_payload_has_no_stream_options() -> None:
    payload = DeepSeekClient._build_payload(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "hi"}],
        stream=False,
        json_mode=False,
        thinking="disabled",
        reasoning_effort=None,
        temperature=0.7,
        max_tokens=100,
    )
    assert "stream_options" not in payload


def test_extract_cache_usage_reads_prefix_cache_tokens() -> None:
    raw = {
        "usage": {
            "prompt_tokens": 30000,
            "completion_tokens": 1500,
            "prompt_cache_hit_tokens": 27000,
            "prompt_cache_miss_tokens": 3000,
        }
    }
    assert extract_cache_usage(raw) == (27000, 3000)
    # 同一 raw 的常规 token 提取仍正常。
    assert extract_usage(raw)[0] == 30000


def test_extract_cache_usage_robust_to_missing() -> None:
    assert extract_cache_usage(None) == (None, None)
    assert extract_cache_usage({"usage": {}}) == (None, None)
    assert extract_cache_usage({}) == (None, None)
