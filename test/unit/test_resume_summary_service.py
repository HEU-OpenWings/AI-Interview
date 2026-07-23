from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.resume_summary_service import ResumeSummaryService


@pytest.fixture
def service() -> ResumeSummaryService:
    return ResumeSummaryService()


LOCAL_RESUME = """
姓名：张三
性别：男
年龄：28
电话：13800138000
邮箱：zhangsan@example.com
所在地：上海
GitHub：https://github.com/zhangsan
LinkedIn：https://www.linkedin.com/in/zhangsan

专业技能：Python、FastAPI、Docker、Kubernetes
语言能力：英语 CET-6
证书：PMP
求职意向：Python 后端工程师
期望薪资：25k-30k
期望工作地点：上海
"""


@pytest.mark.parametrize(
    "content",
    [
        '[{"skills": []}]',
        '```json\n[{"skills": []}]\n```',
        '"summary"',
        "42",
        "true",
        "null",
    ],
)
def test_parse_json_response_rejects_non_object_values(service: ResumeSummaryService, content: str) -> None:
    assert service._parse_json_response(content) is None


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"skills": {"technical": ["Python"]}}', {"skills": {"technical": ["Python"]}}),
        ('```json\n{"skills": {}}\n```', {"skills": {}}),
        ('Result: {"skills": {}}', {"skills": {}}),
    ],
)
def test_parse_json_response_accepts_objects(service: ResumeSummaryService, content: str, expected: dict) -> None:
    assert service._parse_json_response(content) == expected


async def test_extract_summary_retries_after_array_response(
    service: ResumeSummaryService,
) -> None:
    model = AsyncMock()
    first_response = MagicMock(content='[{"skills": []}]')
    expected = {"skills": {"technical": ["Python"]}}
    second_response = MagicMock(content=json.dumps(expected))
    model.ainvoke.side_effect = [first_response, second_response]

    with (
        patch("src.services.resume_summary_service.load_chat_model", return_value=model),
        patch("src.services.resume_summary_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await service.extract_summary("Python developer resume")

    assert result == expected
    assert model.ainvoke.await_count == 2


def test_extract_local_summary_reads_reliable_fields(service: ResumeSummaryService) -> None:
    result = service._extract_local_summary(LOCAL_RESUME)

    assert result["basic_info"] == {
        "name": "张三",
        "gender": "男",
        "age": 28,
        "phone": "13800138000",
        "email": "zhangsan@example.com",
        "location": "上海",
        "github": "https://github.com/zhangsan",
        "linkedin": "https://www.linkedin.com/in/zhangsan",
        "photo_url": None,
    }
    assert result["skills"] == {
        "technical": ["Python", "FastAPI", "Docker", "Kubernetes"],
        "languages": ["英语 CET-6"],
        "certifications": ["PMP"],
    }
    assert result["job_preference"] == {
        "job_intention": "Python 后端工程师",
        "expected_salary": "25k-30k",
        "desired_location": "上海",
    }
    assert result["education"] == []
    assert result["work_experience"] == []
    assert result["project_experience"] == []


def test_extract_local_summary_avoids_unlabeled_identity_guesses(service: ResumeSummaryService) -> None:
    result = service._extract_local_summary("李四\n负责后端平台开发，使用 Python 和 Redis。")

    assert result["basic_info"]["name"] is None
    assert result["basic_info"]["phone"] is None
    assert result["basic_info"]["email"] is None
    assert result["skills"]["technical"] == ["Python", "Redis"]


async def test_extract_summary_uses_local_fallback_when_model_load_fails(
    service: ResumeSummaryService,
) -> None:
    with patch(
        "src.services.resume_summary_service.load_chat_model",
        side_effect=ValueError("provider unavailable"),
    ):
        result = await service.extract_summary(LOCAL_RESUME)

    assert result["basic_info"]["email"] == "zhangsan@example.com"
    assert result["skills"]["technical"] == ["Python", "FastAPI", "Docker", "Kubernetes"]


@pytest.mark.parametrize(
    "side_effect",
    [
        TimeoutError(),
        ConnectionError("network unavailable"),
        RuntimeError("provider rejected the request"),
    ],
)
async def test_extract_summary_uses_local_fallback_after_model_errors(
    service: ResumeSummaryService,
    side_effect: Exception,
) -> None:
    model = AsyncMock()
    model.ainvoke.side_effect = side_effect

    with (
        patch("src.services.resume_summary_service.load_chat_model", return_value=model),
        patch("src.services.resume_summary_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await service.extract_summary(LOCAL_RESUME)

    assert result["job_preference"]["job_intention"] == "Python 后端工程师"
    if isinstance(side_effect, RuntimeError):
        assert model.ainvoke.await_count == 1
    else:
        assert model.ainvoke.await_count == 3


async def test_extract_summary_uses_local_fallback_after_invalid_responses(
    service: ResumeSummaryService,
) -> None:
    model = AsyncMock()
    model.ainvoke.return_value = MagicMock(content='[{"skills": []}]')

    with (
        patch("src.services.resume_summary_service.load_chat_model", return_value=model),
        patch("src.services.resume_summary_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await service.extract_summary(LOCAL_RESUME)

    assert result["basic_info"]["phone"] == "13800138000"
    assert model.ainvoke.await_count == 3
