from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.postgres.models_business import UserResume

MAX_RESUME_MARKDOWN_EXCERPT_CHARS = 1200


def _clean_text(value: Any, limit: int = 200) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _extract_technical_skills(skills_value: Any) -> list[Any]:
    """skills 可能是 {"technical": [...]}、plain list 或其它形态，统一取技能列表。"""
    if isinstance(skills_value, dict):
        skills_value = skills_value.get("technical") or skills_value.get("all") or []
    if isinstance(skills_value, str):
        skills_value = [skills_value]
    if not isinstance(skills_value, list):
        return []
    return [skill for skill in skills_value if isinstance(skill, (str, int, float))]


def _compact_resume_summary(summary_json: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(summary_json, dict) or not summary_json:
        return None

    def _as_list(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    basic_info = summary_json.get("basic_info") or {}
    education = _as_list(summary_json.get("education"))
    work_experience = _as_list(summary_json.get("work_experience"))
    project_experience = _as_list(summary_json.get("project_experience"))
    technical_skills = _extract_technical_skills(summary_json.get("skills"))[:12]
    awards = _as_list(summary_json.get("awards"))[:4]

    def _dict_item(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _list_field(item: dict[str, Any], key: str) -> list[Any]:
        value = item.get(key)
        return value if isinstance(value, list) else []

    return {
        "candidate": {
            "name": _dict_item(basic_info).get("name"),
            "school": _dict_item(education[0]).get("school") if education else None,
            "major": _dict_item(education[0]).get("major") if education else None,
            "current_role": _dict_item(work_experience[0]).get("position") if work_experience else None,
        },
        "recent_work": [
            {
                "company": item.get("company"),
                "position": item.get("position"),
                "duration": item.get("duration"),
                "highlights": [_clean_text(highlight, 120) for highlight in _list_field(item, "highlights")[:2]],
            }
            for item in work_experience[:2]
            if isinstance(item, dict)
        ],
        "projects": [
            {
                "name": item.get("name"),
                "tech_stack": _list_field(item, "tech_stack")[:6],
                "description": _clean_text(item.get("description"), 160),
            }
            for item in project_experience[:3]
            if isinstance(item, dict)
        ],
        "skills": technical_skills,
        "awards": awards,
    }


def _compact_structured_resume(structured_resume: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(structured_resume, dict) or not structured_resume:
        return None

    basic_info = structured_resume.get("basic_info") or {}
    education = structured_resume.get("education") or []
    return {
        "candidate": {
            "name": _clean_text(structured_resume.get("name"), 60),
            "school": basic_info.get("school") or (education[0].get("title") if education else None),
            "major": basic_info.get("major") or (education[0].get("subtitle") if education else None),
            "github": basic_info.get("github"),
        }
    }


def _build_markdown_excerpt(markdown_content: str) -> str:
    content = str(markdown_content or "").strip()
    if len(content) <= MAX_RESUME_MARKDOWN_EXCERPT_CHARS:
        return content
    return f"{content[:MAX_RESUME_MARKDOWN_EXCERPT_CHARS].rstrip()}\n\n[简历正文已截断]"


def build_selected_resume_context_payload(resume_record: UserResume) -> dict[str, Any]:
    markdown_content = resume_record.markdown_content or ""
    # Delay importing resume parsing helpers to avoid pulling router initialization
    # into service imports during application startup and tests.
    from server.routers.resume_router import _build_structured_resume

    structured_resume = _compact_structured_resume(
        _build_structured_resume(markdown_content, resume_record.filename)
    )
    summary_json = _compact_resume_summary(
        resume_record.summary_json if isinstance(resume_record.summary_json, dict) else None
    )
    markdown_excerpt = ""

    if not summary_json and not structured_resume:
        markdown_excerpt = _build_markdown_excerpt(markdown_content)

    if not summary_json and structured_resume:
        markdown_excerpt = _build_markdown_excerpt(markdown_content)

    return {
        "selected_resume_id": resume_record.id,
        "selected_resume_filename": resume_record.filename,
        "selected_resume_summary": summary_json,
        "selected_resume_structured": structured_resume,
        "selected_resume_markdown_excerpt": markdown_excerpt,
    }


def build_selected_resume_prompt_block(
    *,
    selected_resume_filename: str | None = None,
    selected_resume_summary: dict[str, Any] | None = None,
    selected_resume_structured: dict[str, Any] | None = None,
    selected_resume_markdown_excerpt: str | None = None,
) -> str:
    if not any(
        [
            str(selected_resume_filename or "").strip(),
            selected_resume_summary,
            selected_resume_structured,
            str(selected_resume_markdown_excerpt or "").strip(),
        ]
    ):
        return ""

    lines = [
        "",
        "## 当前已注入的候选人简历",
        "系统已在启动阶段注入本轮面试使用的目标简历，请优先基于以下内容提问，不要重复检索“我的简历”。",
    ]

    if selected_resume_filename:
        lines.append(f"- 简历文件：{selected_resume_filename}")

    if selected_resume_summary:
        lines.extend(
            [
                "",
                "### 简历结构化摘要",
                json.dumps(selected_resume_summary, ensure_ascii=False, indent=2),
            ]
        )
    elif selected_resume_structured:
        lines.extend(
            [
                "",
                "### 简历结构化字段",
                json.dumps(selected_resume_structured, ensure_ascii=False, indent=2),
            ]
        )

    excerpt = str(selected_resume_markdown_excerpt or "").strip()
    if excerpt:
        lines.extend(
            [
                "",
                "### 简历正文摘录",
                excerpt,
            ]
        )

    return "\n".join(lines)


async def load_selected_resume_context_payload(
    *,
    db: AsyncSession,
    user_id: int,
    resume_id: int | None,
    strict: bool = False,
) -> dict[str, Any]:
    if not resume_id:
        return {}

    result = await db.execute(
        select(UserResume).where(
            UserResume.id == int(resume_id),
            UserResume.user_id == int(user_id),
        )
    )
    resume_record = result.scalar_one_or_none()
    if resume_record is None:
        if strict:
            raise HTTPException(status_code=404, detail="选中的简历不存在")
        return {}

    return build_selected_resume_context_payload(resume_record)
