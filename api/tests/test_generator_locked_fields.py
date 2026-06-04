from app.schemas.generator import GeneratorChatRequest
from app.services.game_generator import GameGeneratorService


def test_request_accepts_locked_fields():
    req = GeneratorChatRequest(
        user_input="测试",
        confirmed_requirements={"story_background": "占位背景"},
        locked_fields=["story_background"],
    )
    assert req.locked_fields == ["story_background"]


def test_request_locked_fields_defaults_empty():
    req = GeneratorChatRequest(user_input="测试")
    assert req.locked_fields == []


def test_interview_messages_include_locked_instruction():
    req = GeneratorChatRequest(
        user_input="测试",
        confirmed_requirements={"story_background": "占位背景"},
        locked_fields=["story_background"],
    )
    messages = GameGeneratorService._build_interview_messages("PROMPT", req)
    joined = "\n".join(m["content"] for m in messages)
    assert "锁定" in joined
    assert "story_background" in joined


def test_interview_messages_no_locked_section_when_empty():
    req = GeneratorChatRequest(user_input="测试", confirmed_requirements={})
    messages = GameGeneratorService._build_interview_messages("PROMPT", req)
    joined = "\n".join(m["content"] for m in messages)
    assert "用户已锁定" not in joined
