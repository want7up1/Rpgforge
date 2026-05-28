"""extract_partial_json_string_field 测试。

这是流式回合时从未闭合的 JSON 中实时提取 narrative 的核心函数（前端边生成边
显示靠它）。纯函数，不依赖 DB。
"""

from app.services.turn_jobs import extract_partial_json_string_field as extract


def test_complete_value() -> None:
    assert extract('{"narrative":"门槛有泥痕"}', "narrative") == "门槛有泥痕"


def test_partial_unterminated_value() -> None:
    # 流式中途：字符串还没闭合也要能取出已收到的部分
    assert extract('{"narrative":"门槛有泥', "narrative") == "门槛有泥"


def test_whitespace_after_colon() -> None:
    assert extract('{"narrative":   "hi"}', "narrative") == "hi"


def test_escaped_quote() -> None:
    assert extract('{"narrative":"他说\\"走\\""}', "narrative") == '他说"走"'


def test_escaped_newline_and_backslash() -> None:
    assert extract('{"narrative":"a\\nb\\\\c"}', "narrative") == "a\nb\\c"


def test_unicode_escape() -> None:
    assert extract('{"narrative":"\\u4f60\\u597d"}', "narrative") == "你好"


def test_field_absent() -> None:
    assert extract('{"visible_clues":[]}', "narrative") == ""


def test_value_not_started() -> None:
    # 还没到值的引号
    assert extract('{"narrative":', "narrative") == ""
    assert extract('{"narrative":   ', "narrative") == ""


def test_field_after_other_fields() -> None:
    content = '{"visible_clues":["x"],"narrative":"正文"}'
    assert extract(content, "narrative") == "正文"


def test_non_string_value_returns_empty() -> None:
    # narrative 不是字符串（异常情况）应安全返回空
    assert extract('{"narrative":123}', "narrative") == ""


def test_trailing_unicode_escape_incomplete() -> None:
    # 流式中途断在 unicode 转义中间，应安全停止而非崩溃
    out = extract('{"narrative":"abc\\u4f', "narrative")
    assert out == "abc"
