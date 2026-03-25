import asyncio
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from src.knowledge.indexing import process_file_to_markdown
from src.knowledge.utils import calculate_content_hash
from src.models.chat import select_model
from src.plugins.document_processor_base import DocumentProcessorException
from src.services.openviking_service import openviking_service
from src.storage.minio import aupload_file_to_minio, get_minio_client
from src.storage.postgres.models_business import User, UserResume
from src.utils import logger

resume = APIRouter(prefix="/resume", tags=["resume"])

SECTION_KEYWORDS = {
    "education": ["教育经历", "教育背景", "教育", "education"],
    "work": ["工作经历", "实习经历", "工作经验", "职业经历", "experience"],
    "project": ["项目经历", "项目经验", "项目", "projects", "project"],
    "skills": ["技能", "专业技能", "技能特长", "skills", "skill"],
    "awards": ["获奖情况", "荣誉奖项", "奖励荣誉", "获奖经历", "awards", "honors", "荣誉"],
}

LABELED_FIELDS = {
    "school": ["学校", "院校", "毕业院校"],
    "major": ["专业"],
    "degree": ["学历", "学位"],
    "grade": ["年级"],
    "location": ["所在地", "居住地", "城市"],
    "intention": ["求职意向", "意向岗位", "应聘岗位"],
    "github": ["Github 账号", "GitHub 账号", "Github账号", "GitHub账号", "Github", "GitHub"],
    "phone": ["联系电话", "手机", "手机号", "电话"],
    "email": ["电子邮箱", "邮箱", "Email", "E-mail", "email", "mail"],
    "wechat": ["微信", "wechat", "WeChat"],
    "work_years": ["工作年限"],
}

ALL_FIELD_LABELS = [label for labels in LABELED_FIELDS.values() for label in labels]

SECTION_KEYWORDS["work"].extend(["校园经历", "实践经历", "社团经历", "学生工作", "社会实践", "在校经历"])
SECTION_KEYWORDS["project"].extend(["项目实践", "开源项目", "科研项目", "作品"])
SECTION_KEYWORDS["awards"].extend(["竞赛获奖", "奖项", "获奖荣誉"])

DATE_REGEX = re.compile(
    r"(((?:19|20)\d{2}|(?:19|20)[xX]{2})(?:[./-](?:\d{1,2}|[xX]{1,2})|\u5e74\s*(?:\d{1,2}|[xX]{1,2})\u6708?)?"
    r"(?:\s*(?:-|–|—|~|\u81f3|\u5230)\s*(?:\u81f3\u4eca|\u73b0\u5728|Present|present|Current|current|"
    r"((?:19|20)\d{2}|(?:19|20)[xX]{2})(?:[./-](?:\d{1,2}|[xX]{1,2})|\u5e74\s*(?:\d{1,2}|[xX]{1,2})\u6708?)?))?)",
    re.I,
)

RESUME_LLM_MAX_CHARS = 18000
RESUME_STRUCTURED_CACHE_MAX_ITEMS = 256
RESUME_STRUCTURED_CACHE: dict[str, dict[str, Any]] = {}
RESUME_STRUCTURED_CACHE_VERSION = "v15"
RESUME_LLM_DISABLED = False
RESUME_LLM_DISABLED_UNTIL = 0.0
RESUME_LLM_RETRY_COOLDOWN_SECONDS = 180
RESUME_PARSER_MINERU_FALLBACK_MARGIN = 18.0

RESUME_SECTION_HINTS = (
    "education",
    "experience",
    "project",
    "skills",
    "awards",
    "教育",
    "工作",
    "实习",
    "项目",
    "技能",
    "获奖",
)

RESUME_FIELD_HINTS = ("学校", "专业", "学历", "学位", "公司", "岗位", "电话", "邮箱")
RESUME_BROKEN_HEADER_PATTERNS = (
    r"教育经\s*\n\s*历",
    r"工作经\s*\n\s*历",
    r"实习经\s*\n\s*历",
    r"项目经\s*\n\s*历",
    r"校园经\s*\n\s*历",
    r"获奖经\s*\n\s*历",
)

SCHOOL_NAME_HINTS = ("大学", "学院", "学校", "中学", "University", "College", "Institute")
NAME_STOPWORDS = (
    "简历",
    "个人",
    "产品",
    "校园",
    "大使",
    "实习",
    "工程",
    "技术",
    "开发",
    "测试",
    "运营",
    "岗位",
    "应聘",
    "求职",
    "AI",
)

EDU_SCHOOL_REGEX = re.compile(r"([\u4e00-\u9fffA-Za-z·]{2,40}(?:大学|学院|学校|中学))")
EDU_MAJOR_REGEX = re.compile(
    r"([\u4e00-\u9fffA-Za-z]{2,30}(?:专业|科学|技术|管理|法学|文学|数学|统计|金融|会计))"
)
PROTOCOL_NOISE_REGEX = re.compile(r"^协议[：:；;].*(?:post|get|header|delete|json|xml|xpath)", re.I)


def _normalize_text_whitespace(text: str = "") -> str:
    return re.sub(r"[ \t]+", " ", text or "").strip()


def _sanitize_numeric_artifacts(text: str = "") -> str:
    value = str(text or "")
    if not value:
        return ""

    def _unwrap_math_token(match: re.Match[str]) -> str:
        inner = _normalize_text_whitespace(match.group(1))
        number_match = re.search(r"\d(?:[\d\s]{0,20}\d)?\s*[+\-]?\s*[%％]?", inner)
        if number_match:
            return re.sub(r"\s+", "", number_match.group(0)).replace("＋", "+")
        return inner

    value = re.sub(r"\$\s*\{([^{}]+)\}\s*\$", _unwrap_math_token, value)
    value = re.sub(r"\$\s*\^\s*\{([^{}]+)\}\s*\$", _unwrap_math_token, value)
    value = re.sub(r"\$\s*\\?[A-Za-z]+\s*\{([^{}]+)\}\s*\$", _unwrap_math_token, value)
    value = value.replace("\\", "")
    value = re.sub(r"\$\s*\{?\s*(\d+(?:\.\d+)?)\s*([+\-]?)\s*[%％]?\s*\}?\s*\$", r"\1\2", value)
    value = re.sub(r"(?<=\d)\s+(?=\d)", "", value)
    value = re.sub(r"(?<=\d)\s*[$#*{}]+\s*", "", value)
    value = re.sub(r"[$#*{}]+(?=\s*\d)", "", value)
    value = re.sub(r"(?<=[\d+\-])\s*\$", "", value)
    value = re.sub(r"\$(?=\s*[\d+\-])", "", value)
    value = value.replace("$", "")
    value = re.sub(r"(?<=\d)\s*[%％](?=\s*[+\-]?$)", "", value)
    return _normalize_text_whitespace(value)


def _sanitize_name_text(text: str = "") -> str:
    value = _sanitize_numeric_artifacts(text)
    value = re.sub(r"^[#/*|·•\-\s]+", "", value)
    value = re.sub(r"^[\W_]+", "", value, flags=re.U)
    return value.strip()


def _strip_leading_marker(text: str = "") -> str:
    value = _normalize_text_whitespace(_sanitize_numeric_artifacts(text or ""))
    if not value:
        return ""
    value = re.sub(r"^\s*[#*•·]+\s*", "", value)
    value = re.sub(r"^\s*(?:\d+|[一二三四五六七八九十]+)\s*[.)、:：]?\s*", "", value)
    value = re.sub(r"^(?:diamondsuit|textcircled\d+)\s*", "", value, flags=re.I)
    return value.strip()


def _is_protocol_noise_line(text: str = "") -> bool:
    value = _normalize_text_whitespace(_sanitize_numeric_artifacts(text or ""))
    if not value:
        return False
    return bool(PROTOCOL_NOISE_REGEX.search(value))


def _extract_school_from_text(text: str = "") -> str:
    value = _normalize_text_whitespace(_sanitize_numeric_artifacts(text or ""))
    if not value:
        return ""
    match = EDU_SCHOOL_REGEX.search(value)
    return match.group(1).strip() if match else ""


def _extract_major_from_text(text: str = "") -> str:
    value = _normalize_text_whitespace(_sanitize_numeric_artifacts(text or ""))
    if not value:
        return ""
    if re.search(r"(求职意向|意向岗位|应聘岗位)", value) and "专业" not in value and "主修" not in value:
        return ""
    labeled = re.search(r"(?:专业|主修)\s*[:：]\s*([^，,。；;\s]{2,30})", value)
    if labeled:
        return labeled.group(1).strip()
    match = EDU_MAJOR_REGEX.search(value)
    return match.group(1).strip() if match else ""


def _is_bullet_line(line: str = "") -> bool:
    value = _normalize_text_whitespace(line)
    if not value:
        return False
    return bool(re.match(r"^(?:[-*•·]|\d+[.)、]|[（(]?\d+[）)]|[一二三四五六七八九十]+[、.])", value))


def _looks_like_school_text(text: str = "") -> bool:
    value = _normalize_text_whitespace(text)
    if not value:
        return False
    return any(hint in value for hint in SCHOOL_NAME_HINTS)


def _looks_like_major_text(text: str = "") -> bool:
    value = _normalize_text_whitespace(text)
    if not value:
        return False
    major_hints = (
        "专业",
        "本科",
        "硕士",
        "博士",
        "计算机",
        "软件",
        "人工智能",
        "工程",
        "管理",
        "金融",
        "法学",
        "经济",
        "统计",
        "数学",
        "英语",
        "物联网",
    )
    return any(hint in value for hint in major_hints)


def _looks_like_timeline_title(line: str = "") -> bool:
    value = _normalize_text_whitespace(line)
    if not value:
        return False
    if _looks_like_date_range(value) or _is_noise_timeline_title(value) or _is_bullet_line(value):
        return False
    if len(value) > 80:
        return False
    if value.endswith(("。", "；", ";")):
        return False
    if "：" in value or ":" in value:
        if any(prefix in value for prefix in ("公司属性", "项目简介", "个人工作", "核心工作", "主要职责")):
            return False
    if "|" in value or "·" in value:
        return True
    if re.search(r"(大学|学院|公司|集团|项目|俱乐部|社团|协会|实习生|工程师|助理|成员|副社长|社长)$", value):
        return True
    return len(value) <= 28 and not re.search(r"[：。；;]", value)


def _merge_continuation_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    for raw in lines:
        line = _normalize_text_whitespace(raw)
        if not line:
            continue
        if (
            merged
            and not _is_bullet_line(line)
            and not _looks_like_date_range(line)
            and not _looks_like_timeline_title(line)
            and not re.search(r"[。；;]$", merged[-1])
        ):
            merged[-1] = f"{merged[-1]}{line}"
            continue
        merged.append(line)
    return merged


def _normalize_award_compare_text(text: str = "") -> str:
    value = _sanitize_numeric_artifacts(text or "")
    value = re.sub(r"^\s*(?:荣获|获得|获)\s*", "", value)
    value = re.sub(r"[\s:：,，。；;、()（）【】\[\]<>《》·\-—_]+", "", value)
    return value.lower()


def _is_award_like_text(text: str = "") -> bool:
    value = _sanitize_numeric_artifacts(text or "")
    if not value:
        return False
    return bool(
        re.search(
            r"(?:\u83b7\u5956|\u8363\u8a89|\u79f0\u53f7|\u4e00\u7b49\u5956|\u4e8c\u7b49\u5956|\u4e09\u7b49\u5956|\u91d1\u5956|\u94f6\u5956|\u94dc\u5956|\u5956\u5b66\u91d1|\u7ade\u8d5b|\u5927\u8d5b|\u8bc1\u4e66|\u4f18\u79c0)",
            value,
            re.I,
        )
    )


def _split_skills_and_awards(skills: list[str]) -> tuple[list[str], list[str]]:
    pure_skills: list[str] = []
    awards: list[str] = []
    seen_skill: set[str] = set()
    seen_award: set[str] = set()

    for raw in skills:
        token = _sanitize_numeric_artifacts(raw or "")
        if not token:
            continue
        if _is_award_like_text(token):
            award_key = _normalize_award_compare_text(token)
            if award_key and award_key not in seen_award:
                seen_award.add(award_key)
                awards.append(token)
            continue
        key = token.lower()
        if key in seen_skill:
            continue
        seen_skill.add(key)
        pure_skills.append(token)

    return pure_skills, awards


def _extract_name_core(text: str = "") -> str:
    value = _sanitize_name_text(text)
    if not value:
        return ""

    value = re.sub(r"^(?:\u59d3\u540d|name)\s*[:\uff1a]\s*", "", value, flags=re.I)
    value = re.split(
        r"(?:\u6c42\u804c\u610f\u5411|\u5de5\u4f5c\u5e74\u9650|\u8054\u7cfb\u7535\u8bdd|\u7535\u8bdd|\u624b\u673a|\u90ae\u7bb1|\u5fae\u4fe1|github|\u5b66\u6821|\u6bd5\u4e1a\u9662\u6821|\u6027\u522b|\u5e74\u9f84)",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    value = value.strip(" :：|/,，；;")
    if not value:
        return ""

    chinese_match = re.search(r"[\u4e00-\u9fff]{2,4}", value)
    if chinese_match:
        candidate = chinese_match.group(0)
        if not any(stop in candidate for stop in NAME_STOPWORDS):
            return candidate

    latin_match = re.search(r"[A-Za-z][A-Za-z .'\-]{1,39}", value)
    if latin_match:
        return latin_match.group(0).strip()

    fallback = value[:20].strip()
    if any(stop in fallback for stop in NAME_STOPWORDS):
        return ""
    return fallback


def _derive_projects_from_timeline_items(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    seen: set[str] = set()
    project_hint = re.compile(r"(?:\u9879\u76ee|\u5f00\u53d1|\u7cfb\u7edf|\u5e73\u53f0|\u524d\u7aef|\u540e\u7aef)", re.I)
    strong_tech = re.compile(r"(?:\u7cfb\u7edf|\u5e73\u53f0|\u6a21\u578b|\u6846\u67b6|\u52a9\u624b|RAG|API|\u6570\u636e\u96c6)", re.I)
    campus_noise = re.compile(r"(?:\u6821\u56ed|\u793e\u56e2|\u5b66\u751f\u4f1a|\u5b66\u9662|\u6821\u7ea7|\u7acb\u9879|\u8d5b\u4e8b|\u6821\u53cb)")

    for group in groups:
        for item in group:
            if not isinstance(item, dict):
                continue
            title = _pick_best_string(item.get("title"))
            subtitle = _pick_best_string(item.get("subtitle"))
            details = _ensure_string_list(item.get("details"))
            lines = [part for part in [title, subtitle, *details] if part]
            if not lines:
                continue

            project_lines = [
                line
                for line in lines
                if project_hint.search(line)
                and not _is_award_like_text(line)
                and not (campus_noise.search(line) and not strong_tech.search(line))
            ]
            if not project_lines:
                continue

            candidate_title = ""
            for line in lines:
                stripped = re.sub(r"^\s*\d+[.、]\s*", "", line).strip()
                if len(stripped) < 2:
                    continue
                if re.fullmatch(r"[+\-*/_|~.]+", stripped):
                    continue
                if "\u9879\u76ee" in stripped and len(stripped) <= 40 and not re.search(r"[，。；;]", stripped):
                    if campus_noise.search(stripped) and not strong_tech.search(stripped):
                        continue
                    candidate_title = stripped
                    break
            if not candidate_title:
                candidate_title = "\u9879\u76ee\u5b9e\u8df5"

            key = _normalize_title(f"{candidate_title}|{project_lines[0]}")
            if not key or key in seen:
                continue
            seen.add(key)

            projects.append(
                {
                    "title": candidate_title,
                    "subtitle": "",
                    "date": _pick_best_string(item.get("date")),
                    "details": _merge_unique_strings(project_lines[:6]),
                }
            )

    return projects


def _looks_like_skill_line(text: str = "") -> bool:
    value = _sanitize_numeric_artifacts(text or "")
    if not value:
        return False
    return bool(re.search(r"(?:HTML|CSS|JavaScript|TypeScript|React|Vue|Angular|Python|Java|SQL|Git|Webpack|Gulp|CET-\d)", value, re.I))


def _derive_campus_from_projects(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    campus: list[dict[str, Any]] = []
    campus_keywords = ("校园", "社团", "学生会", "协会", "俱乐部", "学院", "学校", "宣传", "外联", "团委")

    for project in projects:
        if not isinstance(project, dict):
            continue
        title = _pick_best_string(project.get("title"))
        subtitle = _pick_best_string(project.get("subtitle"))
        date = _pick_best_string(project.get("date"))
        details = _ensure_string_list(project.get("details"))
        lines = [part for part in [title, subtitle, *details] if part]
        if not lines:
            continue

        campus_lines = [line for line in lines if any(keyword in line for keyword in campus_keywords)]
        if not campus_lines:
            continue

        campus_title = re.sub(r"^\s*\d+[.、]\s*", "", campus_lines[0]).strip()
        if not campus_title:
            continue
        campus_details = [
            line
            for line in lines
            if line != campus_lines[0] and not _looks_like_skill_line(line) and not _is_award_like_text(line)
        ]
        campus.append(
            {
                "title": campus_title,
                "subtitle": "",
                "date": date,
                "details": _merge_unique_strings(campus_details[:6]),
            }
        )
        if campus:
            break

    return campus


def _extract_award_rank_tail(text: str = "") -> str:
    value = _sanitize_numeric_artifacts(text or "")
    match = re.search(r"([^，,。；;]{0,40}(?:特等奖|一等奖|二等奖|三等奖|金奖|银奖|铜奖|冠军|亚军|优秀奖))", value)
    if not match:
        return ""
    return _normalize_award_compare_text(match.group(1).replace("系列", "").replace("创新", ""))


def _dedupe_award_strings(raw_awards: list[str]) -> list[str]:
    deduped: list[str] = []
    for raw in raw_awards:
        candidate = _sanitize_numeric_artifacts(raw or "")
        candidate = re.sub(r"^\s*[#/*|·•+\s]+", "", candidate).strip()
        if not candidate:
            continue
        key = _normalize_award_compare_text(candidate)
        if not key:
            continue
        replaced = False
        for index, existing in enumerate(deduped):
            existing_key = _normalize_award_compare_text(existing)
            existing_tail = _extract_award_rank_tail(existing)
            current_tail = _extract_award_rank_tail(candidate)
            if (
                key == existing_key
                or key in existing_key
                or existing_key in key
                or (current_tail and existing_tail and (current_tail == existing_tail or current_tail in existing_tail or existing_tail in current_tail))
            ):
                if len(candidate) > len(existing):
                    deduped[index] = candidate
                replaced = True
                break
        if not replaced:
            deduped.append(candidate)
    return deduped


def _text_quality_score(text: str = "") -> float:
    value = text or ""
    stripped = value.strip()
    if not stripped:
        return -1e9

    length_score = min(len(stripped), 12000) / 12000 * 45
    line_count = len([line for line in stripped.splitlines() if line.strip()])
    line_score = min(line_count, 280) / 280 * 8

    section_hits = sum(1 for key in RESUME_SECTION_HINTS if key.lower() in stripped.lower())
    section_score = min(section_hits, 10) * 3

    field_hits = sum(1 for key in RESUME_FIELD_HINTS if key in stripped)
    field_score = min(field_hits, 6) * 2.5

    date_hits = len(re.findall(r"(?:19|20)\d{2}(?:[./-]\d{1,2})?", stripped))
    date_score = min(date_hits, 24) * 0.45

    phone_hit = 3 if re.search(r"(?:\+?86[-\s]?)?(?:1[3-9]\d{9}|\d{3,4}[-\s]?\d{7,8})", stripped) else 0
    email_hit = 3 if re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,10}", stripped, re.I) else 0

    invalid_chars = stripped.count("\ufffd")
    invalid_penalty = min(invalid_chars * 1.5, 30)
    broken_header_hits = sum(len(re.findall(pattern, stripped, re.I)) for pattern in RESUME_BROKEN_HEADER_PATTERNS)
    broken_header_penalty = min(broken_header_hits * 6, 24)

    return (
        length_score
        + line_score
        + section_score
        + field_score
        + date_score
        + phone_hit
        + email_hit
        - invalid_penalty
        - broken_header_penalty
    )


def _select_best_markdown(candidates: list[tuple[str, str]]) -> tuple[str, str]:
    scored = [(name, text, _text_quality_score(text)) for name, text in candidates]

    mineru_item = next((item for item in scored if item[0] == "mineru_official"), None)
    if mineru_item:
        _, _, mineru_score = mineru_item
        best_non_mineru = max(
            (item for item in scored if item[0] != "mineru_official"),
            key=lambda item: item[2],
            default=None,
        )
        if best_non_mineru is None or mineru_score >= (best_non_mineru[2] - RESUME_PARSER_MINERU_FALLBACK_MARGIN):
            return mineru_item[0], mineru_item[1]

    best_name, best_text, _ = max(scored, key=lambda item: item[2])
    return best_name, best_text


def _extract_json_object(text: str = "") -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None

    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.I)
    if code_block:
        raw = code_block.group(1).strip()

    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None

    try:
        parsed = json.loads(raw[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _model_message_to_text(message: Any) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


def _normalize_month(value: str = "") -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered in {"present", "current", "now"}:
        return "\u81f3\u4eca"
    if raw in {"\u81f3\u4eca", "\u73b0\u5728"}:
        return "\u81f3\u4eca"

    date_match = re.search(r"((?:19|20)\d{2}|(?:19|20)[xX]{2})(?:[./-]|\u5e74)?\s*(\d{1,2}|[xX]{1,2})?", raw)
    if not date_match:
        year_match = re.search(r"(?:19|20)\d{2}|(?:19|20)[xX]{2}", raw)
        return year_match.group(0) if year_match else raw

    year = date_match.group(1)
    month = date_match.group(2)
    if not month:
        return year
    if re.fullmatch(r"[xX]{1,2}", month):
        return f"{year.lower()}-xx"
    month_int = max(1, min(12, int(month)))
    return f"{year.lower()}-{month_int:02d}"


def _parse_date_span(start_time: str = "", end_time: str = "") -> str:
    start = _normalize_month(start_time)
    end = _normalize_month(end_time)
    if start and end:
        return f"{start} - {end}"
    if start:
        return f"{start} - \u81f3\u4eca"
    return end


def _ensure_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            cleaned = _sanitize_numeric_artifacts(str(item or ""))
            if cleaned:
                result.append(cleaned)
        return result
    if isinstance(value, str):
        parts = re.split(r"[,\uff0c\u3001;/|]", value)
        return [cleaned for cleaned in (_sanitize_numeric_artifacts(part) for part in parts) if cleaned]
    return []


def _pick_best_string(*values: Any) -> str:
    for value in values:
        text = _sanitize_numeric_artifacts(str(value or ""))
        if text:
            return text
    return ""


def _merge_skills(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            cleaned = _normalize_text_whitespace(item)
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(cleaned)
    return merged


def _build_rule_based_experience(work_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    experience: list[dict[str, Any]] = []
    for item in work_items:
        span = item.get("date", "")
        dates = [token.strip() for token in re.split(r"\s*(?:-|–|—|~|至|到)\s*", span) if token.strip()]
        start_time = _normalize_month(dates[0]) if dates else ""
        end_time = _normalize_month(dates[1]) if len(dates) > 1 else ""
        experience.append(
            {
                "company": _pick_best_string(item.get("title")),
                "role": _pick_best_string(item.get("subtitle")),
                "start_time": start_time,
                "end_time": end_time,
                "description": _ensure_string_list(item.get("details")),
            }
        )
    return [item for item in experience if any(item.values())]


def _is_noise_timeline_title(title: str = "") -> bool:
    raw = _strip_leading_marker(title or "")
    value = _normalize_title(raw)
    if not value:
        return True
    noise_keys = {
        _normalize_title("核心工作"),
        _normalize_title("个人工作"),
        _normalize_title("工作内容"),
        _normalize_title("主要职责"),
        _normalize_title("个人评价"),
        _normalize_title("自我评价"),
        _normalize_title("个人技能"),
        _normalize_title("技能"),
        _normalize_title("教育经历"),
        _normalize_title("教育背景"),
        _normalize_title("工作经历"),
        _normalize_title("项目经历"),
        _normalize_title("项目经验"),
    }
    if value in noise_keys:
        return True
    if value in {"diamondsuit", "textcircled"}:
        return True
    if _is_protocol_noise_line(raw):
        return True
    if re.search(r"(?:\u5f00\u59cb|\u8d77\u59cb).{0,8}(?:\u7ed3\u675f|\u622a\u6b62)", raw, re.I):
        return True
    if re.fullmatch(r"[+\-*/_|~.\s]+", raw):
        return True
    if re.fullmatch(
        r"(?:(?:19|20)\d{2}|(?:19|20)[xX]{2})(?:[./-](?:\d{1,2}|[xX]{1,2}))?\s*(?:-|–|—|~|\u81f3|\u5230)\s*(?:(?:19|20)\d{2}|(?:19|20)[xX]{2}|(?:\u81f3\u4eca|\u73b0\u5728))",
        raw,
        re.I,
    ):
        return True
    cleaned = re.sub(r"[:：]+$", "", value)
    return cleaned in noise_keys


def _is_campus_experience_item(item: dict[str, Any]) -> bool:
    title = _normalize_title(_pick_best_string(item.get("title"), item.get("company")))
    subtitle = _normalize_title(_pick_best_string(item.get("subtitle"), item.get("role")))
    details = _normalize_title(" ".join(_ensure_string_list(item.get("details") or item.get("description") or [])))
    full = f"{title} {subtitle} {details}"

    campus_keywords = (
        "校园",
        "社团",
        "学生会",
        "协会",
        "俱乐部",
        "学院",
        "学校",
        "校友会",
        "志愿",
        "组织部",
        "宣传部",
        "部长",
        "副社长",
        "社长",
        "班级",
        "团委",
        "团总支",
        "科协",
    )
    work_keywords = (
        "公司",
        "集团",
        "科技",
        "有限",
        "实习",
        "任职",
        "产品部",
        "研发",
        "工程师",
        "运营",
        "互联网",
        "外包",
    )

    strong_campus = any(k in f"{title} {subtitle}" for k in campus_keywords)
    has_campus = any(k in full for k in campus_keywords)
    has_work = any(k in full for k in work_keywords)
    if strong_campus:
        return True
    return has_campus and not has_work


def _looks_like_role_title(title: str = "") -> bool:
    value = _strip_leading_marker(title or "")
    if not value:
        return False
    if re.search(r"(公司|集团|科技|有限|大学|学院|学校)", value):
        return False
    return bool(re.search(r"(岗位|职位|实习生|工程师|经理|主管|测试|开发)", value))


def _timeline_item_score(item: dict[str, Any]) -> int:
    details = item.get("details") or []
    score = len(details) * 10
    if item.get("subtitle"):
        score += 4
    if item.get("date"):
        score += 3
    if item.get("title") and not _looks_like_role_title(item.get("title", "")):
        score += 2
    return score


def _cleanup_project_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _strip_leading_marker(_pick_best_string(item.get("title")))
        subtitle = _strip_leading_marker(_pick_best_string(item.get("subtitle")))
        date = _pick_best_string(item.get("date"))
        details = [_strip_leading_marker(line) for line in _ensure_string_list(item.get("details")) if _strip_leading_marker(line)]

        title = re.sub(r"^(?:项目描述|项目简介|项目职责)\s*[:：]\s*", "", title, flags=re.I).strip()
        if not title or _is_protocol_noise_line(title):
            continue

        looks_like_content_title = (
            len(title) > 42 and bool(re.search(r"[，。；;]", title))
        ) or bool(re.match(r"^(?:负责|完成|参与|掌握|熟悉|配合|协助|推动|主导)", title))
        campus_noise = bool(re.search(r"(校园|社团|学生会|学院|校级|立项|赛事|大赛|答疑|赛程)", title))
        tech_signal = bool(re.search(r"(系统|平台|模型|框架|助手|开发|RAG|API|数据集)", title, re.I))
        if campus_noise and not tech_signal:
            looks_like_content_title = True

        if looks_like_content_title:
            # Only merge content-like titles when they are true continuation fragments.
            if cleaned and (not date or cleaned[-1].get("date") == date):
                cleaned[-1]["details"] = _merge_unique_strings(cleaned[-1].get("details", []), [title, *details])
                if date and not cleaned[-1].get("date"):
                    cleaned[-1]["date"] = date
                continue
            if tech_signal:
                # With a date but no reliable project heading, this is usually malformed content.
                # Prefer dropping it and rely on contextual parser for the actual project title.
                if date and cleaned:
                    continue
                details = [title, *details]
                title = "项目实践"
            else:
                continue

        cleaned.append(
            {
                "title": title,
                "subtitle": subtitle,
                "date": date,
                "details": details,
            }
        )

    if not cleaned:
        return []

    dedup: dict[tuple[str, str], dict[str, Any]] = {}
    for item in cleaned:
        key = (_normalize_title(item.get("title", "")), _normalize_text_whitespace(item.get("date", "")))
        existed = dedup.get(key)
        if existed is None or _timeline_item_score(item) > _timeline_item_score(existed):
            dedup[key] = item

    return list(dedup.values())


def _split_work_and_campus(work_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    work: list[dict[str, Any]] = []
    campus: list[dict[str, Any]] = []
    for item in work_items:
        title = _pick_best_string(item.get("title"), item.get("company"))
        if _is_noise_timeline_title(title):
            continue
        if _is_campus_experience_item(item):
            campus.append(item)
        else:
            work.append(item)
    return work, campus


def _clean_inline_text(value: str = "") -> str:
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = value.replace("`", "").replace("**", "").replace("__", "")
    value = re.sub(r"^\s*>+\s?", "", value)
    value = re.sub(r"^\s*#{1,6}\s*", "", value)
    return _sanitize_numeric_artifacts(value.strip())


def _normalize_title(value: str = "") -> str:
    normalized = _clean_inline_text(value)
    normalized = re.sub(r"^#+\s*", "", normalized)
    normalized = re.sub(r"^\d+\s*", "", normalized)
    normalized = re.sub(r"[：:]", "", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.lower()


def _is_markdown_table_divider(line: str = "") -> bool:
    return bool(re.match(r"^\s*\|?[\s:-]+(?:\|[\s:-]+)+\|?\s*$", line))


def _is_markdown_table_row(line: str = "") -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _split_table_cells(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    if not stripped:
        return []
    return [_clean_inline_text(cell) for cell in stripped.split("|")]


def _match_section_key(line: str = "") -> str | None:
    normalized = _normalize_title(line)
    if not normalized:
        return None

    best_key = None
    best_score = 0

    for key, keywords in SECTION_KEYWORDS.items():
        for keyword in keywords:
            normalized_keyword = _normalize_title(keyword)
            if not normalized_keyword:
                continue
            if normalized == normalized_keyword:
                score = len(normalized_keyword) + 100
            elif normalized.startswith(normalized_keyword):
                score = len(normalized_keyword) + 50
            elif normalized_keyword in normalized and len(normalized) <= max(24, len(normalized_keyword) * 4):
                score = len(normalized_keyword)
            else:
                continue

            if score > best_score:
                best_key = key
                best_score = score

    return best_key


def _is_probable_section_title(line: str = "", matched_key: str | None = None) -> bool:
    value = _clean_inline_text(line)
    normalized = _normalize_title(value)
    if not normalized:
        return False
    if _looks_like_date_range(value):
        return False
    if re.search(r"[|｜丨]", value):
        return False
    if len(normalized) > 14:
        return False

    key = matched_key or _match_section_key(value)
    if key is None:
        return False
    normalized_keywords = [_normalize_title(keyword) for keyword in SECTION_KEYWORDS[key]]
    if any(normalized == keyword or normalized.startswith(keyword) for keyword in normalized_keywords if keyword):
        return True
    # Keep short alias headings like "相关技能"/"个人技能" as real sections.
    if key in {"skills", "awards"} and len(normalized) <= 10:
        return any(keyword and keyword in normalized for keyword in normalized_keywords)
    return False


def _is_standalone_section_title(line: str = "") -> bool:
    return _is_probable_section_title(line)


def _looks_like_date_range(line: str = "") -> bool:
    return bool(DATE_REGEX.search(line))


def _extract_title_and_date(line: str = "") -> tuple[str, str]:
    match = DATE_REGEX.search(line)
    if not match:
        return _strip_leading_marker(line), ""

    title = line.replace(match.group(0), "")
    title = re.sub(r"[|｜丨]", " ", title)
    title = re.split(r"(?:项目描述|项目简介|项目职责)\s*[:：]", title, maxsplit=1)[0]
    title = _strip_leading_marker(re.sub(r"\s{2,}", " ", title).strip())
    return title, match.group(0).strip()


def _extract_table_blocks(markdown: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []

    for raw_line in markdown.splitlines():
        if _is_markdown_table_row(raw_line) or (_is_markdown_table_divider(raw_line) and current):
            current.append(raw_line)
            continue

        if current:
            blocks.append(current)
            current = []

    if current:
        blocks.append(current)

    return blocks


def _extract_table_column_texts(markdown: str) -> list[str]:
    column_texts: list[str] = []

    for block in _extract_table_blocks(markdown):
        rows = [row for row in block if _is_markdown_table_row(row) and not _is_markdown_table_divider(row)]
        if not rows:
            continue

        parsed_rows = [_split_table_cells(row) for row in rows]
        max_cols = max((len(row) for row in parsed_rows), default=0)
        if max_cols <= 1:
            continue

        columns: list[list[str]] = [[] for _ in range(max_cols)]
        for row in parsed_rows:
            for index, cell in enumerate(row):
                if cell:
                    columns[index].append(cell)

        for column in columns:
            cleaned_lines = []
            for line in column:
                if not line:
                    continue
                if cleaned_lines and cleaned_lines[-1] == line:
                    continue
                cleaned_lines.append(line)
            if cleaned_lines:
                column_texts.append("\n".join(cleaned_lines))

    return column_texts


def _extract_table_pairs(markdown: str) -> dict[str, str]:
    pairs: dict[str, str] = {}

    for block in _extract_table_blocks(markdown):
        for row in block:
            if not _is_markdown_table_row(row) or _is_markdown_table_divider(row):
                continue

            cells = [cell for cell in _split_table_cells(row) if cell]
            if len(cells) < 2:
                continue

            for index in range(0, len(cells) - 1, 2):
                key = re.sub(r"[：:]$", "", cells[index]).strip()
                value = cells[index + 1].strip()
                if key and value and key not in pairs:
                    pairs[key] = value

    return pairs


def _strip_table_lines(markdown: str) -> str:
    lines: list[str] = []
    for raw_line in markdown.splitlines():
        if _is_markdown_table_row(raw_line) or _is_markdown_table_divider(raw_line):
            continue
        lines.append(raw_line)
    return "\n".join(lines).strip()


def _split_markdown_sections(markdown: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] = {"title": "", "key": None, "lines": []}

    def push_current():
        if current["title"] or any(_clean_inline_text(line) for line in current["lines"]):
            sections.append({"title": current["title"], "key": current["key"], "lines": list(current["lines"])})

    for raw_line in markdown.splitlines():
        trimmed = raw_line.strip()
        heading_match = re.match(r"^#{1,6}\s+(.+)$", trimmed)
        section_title = ""
        section_key = None

        if heading_match:
            heading_text = _clean_inline_text(heading_match.group(1))
            heading_key = _match_section_key(heading_text)
            # Keep non-section headings in body lines (e.g. company/school timeline titles).
            if heading_key is None or not _is_probable_section_title(heading_text, heading_key):
                current["lines"].append(raw_line)
                continue
            section_title = heading_text
            section_key = heading_key
        else:
            section_key = _match_section_key(trimmed)
            if section_key and len(_clean_inline_text(trimmed)) <= 32 and _is_probable_section_title(trimmed, section_key):
                section_title = _clean_inline_text(trimmed)

        if not section_title and _is_standalone_section_title(trimmed):
            section_title = _clean_inline_text(trimmed)
            section_key = _match_section_key(section_title)

        if section_title:
            push_current()
            current = {"title": section_title, "key": section_key, "lines": []}
            continue

        current["lines"].append(raw_line)

    push_current()
    return sections


def _find_section(sections: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    return next(
        (
            section
            for section in sections
            if section.get("key") == key
            or any(_normalize_title(keyword) in _normalize_title(section["title"]) for keyword in SECTION_KEYWORDS[key])
        ),
        None,
    )


def _find_sections(sections: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return [
        section
        for section in sections
        if section.get("key") == key
        or any(_normalize_title(keyword) in _normalize_title(section["title"]) for keyword in SECTION_KEYWORDS[key])
    ]


def _lines_to_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []

    for raw_line in lines:
        if _is_markdown_table_divider(raw_line):
            continue

        heading_match = re.match(r"^#{1,6}\s+(.+)$", raw_line.strip())
        if heading_match:
            if current:
                blocks.append(current)
            current = [_clean_inline_text(heading_match.group(1))]
            continue

        cleaned = _clean_inline_text(raw_line)
        cleaned = re.sub(r"^\\s*[-*•·]\\s*", "", cleaned).strip()
        if not cleaned:
            if current:
                blocks.append(current)
                current = []
            continue

        current.append(cleaned)

    if current:
        blocks.append(current)

    return blocks


def _parse_timeline_section(section: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not section:
        return []

    items: list[dict[str, Any]] = []
    pending_date = ""
    for block in _lines_to_blocks(section["lines"]):
        if not block:
            continue

        if len(block) == 1 and _looks_like_date_range(block[0]):
            if items and not items[-1].get("date"):
                items[-1]["date"] = block[0].strip()
            else:
                pending_date = block[0].strip()
            continue

        first_line = block[0] if block else ""

        # Obvious continuation text should merge into previous item.
        if items and not _looks_like_timeline_title(first_line):
            items[-1]["details"] = _merge_unique_strings(items[-1].get("details", []), _merge_continuation_lines(block))
            continue

        title, inline_date = _extract_title_and_date(first_line)
        date = inline_date
        rest = block[1:]

        if not date:
            date_index = next((index for index, line in enumerate(rest) if _looks_like_date_range(line)), -1)
            if date_index >= 0:
                date = rest[date_index].strip()
                rest = [line for index, line in enumerate(rest) if index != date_index]
        if not date and pending_date:
            date = pending_date
            pending_date = ""

        subtitle = ""
        if rest and len(rest[0]) <= 30 and not _looks_like_date_range(rest[0]) and not re.search(r"[。；;]", rest[0]):
            subtitle = rest[0].strip()
            rest = rest[1:]

        details = _merge_continuation_lines([line for line in rest if line])

        if title.strip():
            if _is_noise_timeline_title(title) and items:
                noise_title_key = _normalize_title(title)
                if noise_title_key in {
                    _normalize_title("自我评价"),
                    _normalize_title("个人评价"),
                    _normalize_title("个人总结"),
                }:
                    break
                merged_details: list[str] = []
                if subtitle:
                    merged_details.append(subtitle)
                merged_details.extend(details)
                if merged_details:
                    items[-1]["details"] = _merge_unique_strings(items[-1].get("details", []), merged_details)
                if date and not items[-1].get("date"):
                    items[-1]["date"] = date
                continue
            items.append(
                {
                    "title": title.strip(),
                    "subtitle": subtitle,
                    "date": date,
                    "details": details,
                }
            )

    return items


def _extract_contextual_timeline_items(markdown: str, target_key: str) -> list[dict[str, Any]]:
    lines = (markdown or "").splitlines()
    items: list[dict[str, Any]] = []
    active_key: str | None = None
    pending_date = ""
    index = 0

    while index < len(lines):
        raw = lines[index].strip()
        heading_match = re.match(r"^#{1,6}\s+(.+)$", raw)
        if not heading_match:
            plain = _clean_inline_text(raw)
            if active_key == target_key and _looks_like_date_range(plain):
                pending_date = plain
            index += 1
            continue

        heading = _clean_inline_text(heading_match.group(1))
        matched_key = _match_section_key(heading)
        # Only short section titles switch parsing context.
        if matched_key is not None and len(_normalize_title(heading)) <= 10:
            active_key = matched_key
            index += 1
            continue

        if active_key != target_key:
            index += 1
            continue

        if _looks_like_date_range(heading):
            pending_date = heading
            index += 1
            continue

        details: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            next_line = lines[cursor].strip()
            if re.match(r"^#{1,6}\s+(.+)$", next_line):
                break
            cleaned = _clean_inline_text(lines[cursor])
            cleaned = re.sub(r"^\\s*[-*•·]\\s*", "", cleaned).strip()
            if cleaned:
                details.append(cleaned)
            cursor += 1

        title, date = _extract_title_and_date(heading)
        if not date:
            date_index = next((idx for idx, line in enumerate(details) if _looks_like_date_range(line)), -1)
            if date_index >= 0:
                date = details[date_index].strip()
                details = [line for idx, line in enumerate(details) if idx != date_index]
        if not date and pending_date:
            date = pending_date
            pending_date = ""

        subtitle = ""
        if details and len(details[0]) <= 30 and not _looks_like_date_range(details[0]) and not re.search(r"[。；;]", details[0]):
            subtitle = details[0].strip()
            details = details[1:]
        details = _merge_continuation_lines(details)

        if title.strip():
            # 将“核心工作/个人工作”这类噪声标题并入上一条，避免内容丢失
            if _is_noise_timeline_title(title) and items:
                noise_title_key = _normalize_title(title)
                if noise_title_key in {
                    _normalize_title("自我评价"),
                    _normalize_title("个人评价"),
                    _normalize_title("个人总结"),
                }:
                    active_key = None
                    pending_date = ""
                    index = cursor
                    continue
                merged_details = []
                if subtitle:
                    merged_details.append(subtitle)
                merged_details.extend(details)
                if merged_details:
                    items[-1]["details"] = _merge_unique_strings(items[-1].get("details", []), merged_details)
                if date and not items[-1].get("date"):
                    items[-1]["date"] = date
                index = cursor
                continue

            items.append(
                {
                    "title": title.strip(),
                    "subtitle": subtitle,
                    "date": date,
                    "details": details,
                }
            )
        index = cursor

    return items


def _parse_skill_section(section: dict[str, Any] | None) -> list[str]:
    if not section:
        return []

    skills: list[str] = []
    for line in section["lines"]:
        skills.extend(_extract_skill_tokens_from_line(line))

    return _merge_unique_strings(skills)


def _extract_skill_terms_from_line(line: str = "") -> list[str]:
    value = _clean_inline_text(line or "")
    if not value:
        return []
    terms: list[str] = []
    patterns: list[tuple[str, str]] = [
        (r"selenium", "Selenium"),
        (r"webdriver", "WebDriver"),
        (r"appium", "Appium"),
        (r"testng", "TestNG"),
        (r"jenkins", "Jenkins"),
        (r"\bgit\b", "Git"),
        (r"svn", "SVN"),
        (r"\bsql\b|sql语言", "SQL"),
        (r"linux", "Linux"),
        (r"\bjava\b|java语言", "Java"),
        (r"spring\s*mvc", "Spring MVC"),
        (r"j2ee", "J2EE"),
        (r"\bhtml\b", "HTML"),
        (r"\bcss\b", "CSS"),
        (r"javascript|\bjs\b", "JavaScript"),
        (r"jquery", "jQuery"),
        (r"bootstrap", "Bootstrap"),
        (r"xpath", "XPath"),
        (r"json", "JSON"),
        (r"postman", "Postman"),
        (r"jmeter|jemeter", "JMeter"),
        (r"fiddler|fiddle", "Fiddler"),
        (r"charles|charls", "Charles"),
        (r"python", "Python"),
        (r"\bvue\b", "Vue"),
        (r"react", "React"),
        (r"typescript", "TypeScript"),
        (r"\brag\b", "RAG"),
        (r"\bllm\b", "LLM"),
        (r"\bagent\b", "Agent"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, value, re.I):
            terms.append(label)

    if "前端" in value:
        terms.append("前端")
    if "后端" in value:
        terms.append("后端")
    if "数据库" in value:
        terms.append("数据库")
    if "自动化测试" in value:
        terms.append("自动化测试")
    if "持续集成" in value:
        terms.append("持续集成")
    if "接口测试" in value:
        terms.append("接口测试")

    return _merge_unique_strings(terms)


def _normalize_skill_token(token: str = "") -> str:
    value = _sanitize_numeric_artifacts(token or "")
    value = re.sub(r"^(?:diamondsuit|textcircled\d+)\s*", "", value, flags=re.I).strip()
    if not value:
        return ""

    normalize_rules: list[tuple[str, str]] = [
        (r"selenium", "Selenium"),
        (r"webdriver", "WebDriver"),
        (r"appium", "Appium"),
        (r"testng", "TestNG"),
        (r"jenkins", "Jenkins"),
        (r"\bgit\b", "Git"),
        (r"svn", "SVN"),
        (r"\bsql\b|sql语言", "SQL"),
        (r"linux", "Linux"),
        (r"\bjava\b|java语言", "Java"),
        (r"spring\s*mvc", "Spring MVC"),
        (r"j2ee", "J2EE"),
        (r"\bhtml\b", "HTML"),
        (r"\bcss\b", "CSS"),
        (r"javascript|\bjs\b", "JavaScript"),
        (r"jquery", "jQuery"),
        (r"bootstrap", "Bootstrap"),
        (r"xpath", "XPath"),
        (r"json", "JSON"),
        (r"postman", "Postman"),
        (r"jmeter|jemeter", "JMeter"),
        (r"fiddler|fiddle", "Fiddler"),
        (r"charles|charls", "Charles"),
        (r"python", "Python"),
        (r"\bvue\b", "Vue"),
        (r"react", "React"),
        (r"typescript", "TypeScript"),
        (r"\brag\b", "RAG"),
        (r"\bllm\b", "LLM"),
        (r"\bagent\b", "Agent"),
    ]
    for pattern, canonical in normalize_rules:
        if re.search(pattern, value, re.I):
            return canonical
    return value


def _looks_like_skill_token(token: str = "") -> bool:
    value = _sanitize_numeric_artifacts(token or "")
    if not value:
        return False
    if re.fullmatch(r"\d{4}(?:[./-]\d{1,2})?", value):
        return False
    if len(value) > 32:
        return False
    if re.search(r"(通过|能够|完成|参与|独立|快速|命令|文档|报告|计划|测试数据)", value) and len(value) > 10:
        return False
    if "的" in value and len(value) > 10:
        return False
    if re.search(
        r"(python|java|javascript|typescript|react|vue|html|css|sql|linux|jenkins|git|svn|selenium|webdriver|appium|testng|jmeter|postman|fiddler|charles|spring|j2ee|xpath|json|xml|rag|llm|agent|coze|axure|xmind|excel|wps|docker|k8s|nginx)",
        value,
        re.I,
    ):
        return True
    if re.search(r"(前端|后端|数据库|自动化测试|持续集成|测试工具|接口测试|框架)", value):
        return True
    return False


def _extract_skill_tokens_from_line(line: str = "", strict: bool = False) -> list[str]:
    cleaned = _clean_inline_text(line)
    cleaned = re.sub(r"^\s*[-*•·]\s*", "", cleaned).strip()
    if not cleaned:
        return []
    cleaned = re.sub(
        r"([一-龥])\s*(AI核心知识|编程与AI工具|前端基础|编程基础|AI相关)\s*[:：]?",
        r"\1|\2|",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"(?:产品工具|办公工具|WPS数据工具|数据库工具|AI核心知识|编程与AI工具|AI编程工具|前端基础|编程基础|AI相关|技术栈|技能)\s*[:：]?",
        "|",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"[。.!！？?]+", "|", cleaned)
    tokens = [item.strip() for item in re.split(r"[、，,；;|/]", cleaned) if item.strip()]

    skills: list[str] = []
    for token in tokens:
        token = re.sub(
            r"^(技能|掌握|熟悉|了解|精通|使用|熟练使用|熟练运用|持续关注|能够|具备|AI编程工具|编程工具)\s*",
            "",
            token,
            flags=re.I,
        )
        token = token.strip("=+-_()（）[]{}【】 ")
        token = re.sub(r"[（(](掌握|熟练|了解|精通)\)?$", "", token, flags=re.I).strip()
        token = _sanitize_numeric_artifacts(token)
        if not token or len(token) > 40:
            continue
        if token in {"个人", "技能", "荣誉"}:
            continue
        if re.fullmatch(r"\d{1,3}", token):
            continue
        if _is_award_like_text(token):
            continue
        if re.search(r"(?:\u8d1f\u8d23|\u5b8c\u6210|\u5b9e\u73b0|\u7ec4\u7ec7|\u53c2\u4e0e|\u652f\u6301|\u8fd0\u7528|\u8fdb\u884c\u9879\u76ee|\u5ba3\u4f20|\u7b56\u5212)", token):
            continue
        token = _normalize_skill_token(token)
        if not token:
            continue
        if strict and not _looks_like_skill_token(token):
            continue
        skills.append(token)

    return skills


def _extract_skills_from_text(markdown: str) -> list[str]:
    skills: list[str] = []
    in_summary = False
    summary_titles = {
        _normalize_title("自我评价"),
        _normalize_title("个人评价"),
        _normalize_title("个人总结"),
    }

    for raw_line in (markdown or "").splitlines():
        stripped = raw_line.strip()
        heading_match = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if heading_match:
            heading = _clean_inline_text(heading_match.group(1))
            heading_norm = _normalize_title(heading)
            if heading_norm in summary_titles:
                in_summary = True
                continue
            if _is_probable_section_title(heading) or _looks_like_timeline_title(heading):
                in_summary = False
            continue

        cleaned = _clean_inline_text(raw_line)
        cleaned = re.sub(r"^\s*[-*•·]\s*", "", cleaned).strip()
        if not cleaned or _is_protocol_noise_line(cleaned) or _is_award_like_text(cleaned):
            continue

        has_skill_hint = bool(
            re.search(
                r"(掌握|熟悉|精通|了解|使用|技术栈|技能|框架|工具|语言|数据库|前端|后端|自动化|测试工具|jenkins|git|svn|sql|linux|java|python|html|css|javascript|typescript|react|vue)",
                cleaned,
                re.I,
            )
        )
        if not in_summary and not has_skill_hint:
            continue

        term_tokens = _extract_skill_terms_from_line(cleaned)
        if term_tokens:
            skills.extend(term_tokens)
            continue
        skills.extend(_extract_skill_tokens_from_line(cleaned, strict=True))

    return _merge_unique_strings(skills)


def _parse_award_section(section: dict[str, Any] | None) -> list[str]:
    if not section:
        return []

    return [" ".join(block).strip() for block in _lines_to_blocks(section["lines"]) if block]


def _extract_awards_from_text(markdown: str) -> list[str]:
    awards: list[str] = []
    patterns = [
        r"(?:荣获|获得|获)\s*[^。；;\n]{0,80}(?:特等奖|一等奖|二等奖|三等奖|金奖|银奖|铜奖|冠军|亚军|优秀奖|奖项|荣誉)",
        r"[^。；;\n]{0,80}(?:特等奖|一等奖|二等奖|三等奖|金奖|银奖|铜奖|冠军|亚军|优秀奖|奖学金|荣誉称号)[^。；;\n]{0,40}",
    ]

    for raw_line in markdown.splitlines():
        line = _normalize_text_whitespace(_clean_inline_text(raw_line))
        if not line:
            continue
        for pattern in patterns:
            match = re.search(pattern, line, re.I)
            if match:
                candidate = _normalize_text_whitespace(match.group(0))
                candidate = re.sub(r"^\s*[#/*|·•+\s]+", "", candidate)
                if candidate:
                    awards.append(candidate)
                break

    return _dedupe_award_strings(_merge_unique_strings(awards))


def _extract_project_clues_from_text(markdown: str) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    skipped_prefixes = (
        "核心能力",
        "技术基础",
        "办公技能",
        "语言能力",
        "个人评价",
        "自我评价",
        "协议",
    )
    campus_noise_pattern = re.compile(r"(校园|社团|学生会|学院|校级|立项|赛事|答疑|赛程|校友)")
    tech_project_pattern = re.compile(r"(项目|系统|平台|模型|框架|助手|开发|RAG|API|数据集)", re.I)

    for raw_line in markdown.splitlines():
        line = _normalize_text_whitespace(_clean_inline_text(raw_line))
        line = _strip_leading_marker(line)
        if not line:
            continue
        if _is_protocol_noise_line(line):
            continue
        if any(line.startswith(prefix) for prefix in skipped_prefixes):
            continue
        if _is_award_like_text(line):
            continue

        title = ""
        if "项目名" in line:
            match = re.search(r"项目名\s*[:：]?\s*([^。；;\n]{4,80})", line)
            if match:
                title = _normalize_text_whitespace(match.group(1))
        elif (
            "项目" in line
            and len(line) <= 70
            and "项目文档" not in line
            and not re.search(r"[，。；;]", line)
            and not re.search(r"(校园|社团|学院|校级|立项|赛事|校友)", line)
        ):
            title = line

        if not title:
            continue
        if campus_noise_pattern.search(title) and not tech_project_pattern.search(title):
            continue
        if re.match(r"^(?:参与|负责|协助|对接|组织)", title):
            continue
        title = _strip_leading_marker(title)
        if len(title) < 2 or len(title) > 60:
            continue
        if re.fullmatch(r"[+\-*/_|~.\s]+", title):
            continue
        if _is_noise_timeline_title(title):
            continue

        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        projects.append(
            {
                "title": title,
                "subtitle": "",
                "date": "",
                "details": [line],
            }
        )

    return projects


def _extract_phone(markdown: str, table_pairs: dict[str, str] | None = None) -> str:
    labeled_phone = _extract_labeled_field(markdown, LABELED_FIELDS["phone"], table_pairs=table_pairs)
    if labeled_phone:
        normalized = _sanitize_numeric_artifacts(labeled_phone)
        match = re.search(r"(?:\+?86[-\s]?)?(?:1[3-9]\d{9}|\d{3,4}[-\s]?\d{7,8})", normalized)
        if match:
            return match.group(0).strip()
        return normalized.rstrip("回").strip()

    match = re.search(r"(?:\+?86[-\s]?)?(?:1[3-9]\d{9}|\d{3,4}[-\s]?\d{7,8})", markdown)
    return match.group(0).strip() if match else ""


def _extract_email(markdown: str, table_pairs: dict[str, str] | None = None) -> str:
    labeled_email = _extract_labeled_field(markdown, LABELED_FIELDS["email"], table_pairs=table_pairs)
    if labeled_email:
        email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,10}", labeled_email, re.I)
        if email_match:
            return email_match.group(0).strip()
        return labeled_email

    match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,10}", markdown, re.I)
    return match.group(0).strip() if match else ""


def _extract_wechat(markdown: str, table_pairs: dict[str, str] | None = None) -> str:
    def normalize_candidate(raw: str = "", allow_phone_like: bool = False) -> str:
        value = _sanitize_numeric_artifacts(raw)
        if not value:
            return ""
        value = re.sub(r"^(?:回|加|联系)?\s*(?:微信|vx|wx|v信)?\s*[:：]?\s*", "", value, flags=re.I)
        match = re.search(r"[A-Za-z0-9_-]{3,32}", value)
        if not match:
            return ""
        candidate = match.group(0).strip("_-")
        if candidate.lower() in {"weixin", "wechat", "wx", "vx"}:
            return ""
        if re.fullmatch(r"\d{11}", candidate) and not allow_phone_like:
            return ""
        return candidate

    labeled = _extract_labeled_field(markdown, LABELED_FIELDS["wechat"], table_pairs=table_pairs)
    if labeled:
        token = normalize_candidate(labeled, allow_phone_like=False)
        if token:
            return token

    match = re.search(r"(?:微信|wechat|WeChat)\s*[:：]?\s*([A-Za-z0-9_-]{3,32})", markdown, re.I)
    if match:
        return normalize_candidate(match.group(1), allow_phone_like=False)
    return ""


def _extract_labeled_field(markdown: str, labels: list[str], table_pairs: dict[str, str] | None = None) -> str:
    table_pairs = table_pairs or {}

    for key, value in table_pairs.items():
        normalized_key = _normalize_title(key)
        if any(_normalize_title(label) == normalized_key or _normalize_title(label) in normalized_key for label in labels):
            return re.sub(r"\s+", " ", value).strip()

    labels_pattern = "|".join(re.escape(label) for label in labels)
    lookahead_labels_pattern = "|".join(re.escape(label) for label in ALL_FIELD_LABELS)
    pattern = rf"(?:{labels_pattern})\s*[:：]\s*(.+?)(?=(?:{lookahead_labels_pattern})\s*[:：]|\n|$)"
    match = re.search(pattern, markdown, re.I | re.S)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()

    for line in markdown.splitlines():
        cleaned = _clean_inline_text(line)
        if not cleaned:
            continue
        for label in labels:
            if cleaned.startswith(label):
                candidate = cleaned[len(label) :].lstrip(":：|- ").strip()
                if candidate:
                    return candidate

    return ""


def _extract_basic_info(markdown: str, table_pairs: dict[str, str] | None = None) -> dict[str, str]:
    basic_info = {
        "school": _extract_labeled_field(markdown, LABELED_FIELDS["school"], table_pairs=table_pairs),
        "major": _extract_labeled_field(markdown, LABELED_FIELDS["major"], table_pairs=table_pairs),
        "degree": _extract_labeled_field(markdown, LABELED_FIELDS["degree"], table_pairs=table_pairs),
        "grade": _extract_labeled_field(markdown, LABELED_FIELDS["grade"], table_pairs=table_pairs),
        "location": _extract_labeled_field(markdown, LABELED_FIELDS["location"], table_pairs=table_pairs),
        "intention": _extract_labeled_field(markdown, LABELED_FIELDS["intention"], table_pairs=table_pairs),
        "github": _extract_labeled_field(markdown, LABELED_FIELDS["github"], table_pairs=table_pairs),
        "wechat": _extract_wechat(markdown, table_pairs=table_pairs),
    }
    if not basic_info["school"]:
        basic_info["school"] = _extract_school_from_text(markdown)
    if not basic_info["major"]:
        basic_info["major"] = _extract_major_from_text(markdown)
    basic_info["intention"] = re.split(r"(?:工作年限)\s*[:：]?", basic_info["intention"], maxsplit=1)[0].strip()
    return basic_info


def _repair_education_timeline(items: list[dict[str, Any]], source_text: str = "") -> list[dict[str, Any]]:
    if not items:
        return []

    fallback_school = _extract_school_from_text(source_text)
    fallback_major = _extract_major_from_text(source_text)
    repaired: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        title = _strip_leading_marker(_pick_best_string(item.get("title")))
        subtitle = _strip_leading_marker(_pick_best_string(item.get("subtitle")))
        date_text = _pick_best_string(item.get("date"))
        details = [_strip_leading_marker(line) for line in _ensure_string_list(item.get("details")) if _strip_leading_marker(line)]

        school = (
            _extract_school_from_text(title)
            or _extract_school_from_text(subtitle)
            or _extract_school_from_text(date_text)
            or next((_extract_school_from_text(line) for line in details if _extract_school_from_text(line)), "")
        )
        major = (
            _extract_major_from_text(subtitle)
            or _extract_major_from_text(title)
            or _extract_major_from_text(date_text)
            or next((_extract_major_from_text(line) for line in details if _extract_major_from_text(line)), "")
        )

        if not school:
            if _looks_like_school_text(title):
                school = title
            elif fallback_school:
                school = fallback_school
        if not major:
            if _looks_like_major_text(subtitle):
                major = subtitle
            elif _looks_like_major_text(title) and title != school:
                major = title
            elif fallback_major:
                major = fallback_major

        clean_date = date_text
        date_match = DATE_REGEX.search(date_text)
        if date_match:
            clean_date = date_match.group(0).strip()

        repaired.append(
            {
                "title": school or title or "教育信息",
                "subtitle": major or subtitle,
                "date": clean_date,
                "details": details,
            }
        )

    return repaired


def _merge_duplicated_education(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index_by_school: dict[str, int] = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        title = _pick_best_string(item.get("title"))
        subtitle = _pick_best_string(item.get("subtitle"))
        date = _pick_best_string(item.get("date"))
        details = _ensure_string_list(item.get("details"))
        school = _extract_school_from_text(title) or title
        school_key = _normalize_title(school)

        if not school_key:
            merged.append({"title": title, "subtitle": subtitle, "date": date, "details": details})
            continue

        if school_key not in index_by_school:
            index_by_school[school_key] = len(merged)
            merged.append({"title": school, "subtitle": subtitle, "date": date, "details": details})
            continue

        target = merged[index_by_school[school_key]]
        target["details"] = _merge_unique_strings(target.get("details", []), details)
        if not target.get("date") and date:
            target["date"] = date
        # Prefer major-looking subtitle, avoid course line taking over major.
        target_subtitle = _pick_best_string(target.get("subtitle"))
        if _looks_like_major_text(subtitle):
            if not target_subtitle or not _looks_like_major_text(target_subtitle):
                target["subtitle"] = subtitle
            elif "专业" in subtitle and "专业" not in target_subtitle:
                target["subtitle"] = subtitle
        elif not target_subtitle and subtitle:
            target["subtitle"] = subtitle

    return merged


def _merge_timeline_items(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, tuple[str, ...]]] = set()

    for group in groups:
        for item in group:
            key = (
                item.get("title", ""),
                item.get("subtitle", ""),
                item.get("date", ""),
                tuple(item.get("details", []) or []),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

    return merged


def _cleanup_timeline_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        title = _strip_leading_marker(_pick_best_string(item.get("title")))
        subtitle = _strip_leading_marker(_pick_best_string(item.get("subtitle")))
        date = _pick_best_string(item.get("date"))
        details = [
            _strip_leading_marker(line)
            for line in _ensure_string_list(item.get("details"))
            if _strip_leading_marker(line) and not _is_protocol_noise_line(line)
        ]

        if _is_noise_timeline_title(title):
            if subtitle and not _is_noise_timeline_title(subtitle):
                title = re.sub(r"^\s*\d+[.、]\s*", "", subtitle).strip()
                subtitle = ""
            elif details:
                title = re.sub(r"^\s*\d+[.、]\s*", "", details[0]).strip()
                details = details[1:]

        if _is_noise_timeline_title(title):
            continue

        if _is_protocol_noise_line(title):
            continue

        cleaned_items.append(
            {
                "title": title,
                "subtitle": subtitle,
                "date": date,
                "details": details,
            }
        )

    if not cleaned_items:
        return []

    # Merge role-only fragments into richer items with the same detail body.
    merged_items: list[dict[str, Any]] = []
    for item in cleaned_items:
        if _looks_like_role_title(item.get("title", "")) and item.get("details"):
            merged = False
            for target in merged_items:
                if target.get("details") == item.get("details") and not _looks_like_role_title(target.get("title", "")):
                    if not target.get("subtitle"):
                        target["subtitle"] = item.get("title", "")
                    merged = True
                    break
            if merged:
                continue
        merged_items.append(item)

    # Dedupe by title/date while keeping the most informative item.
    best_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in merged_items:
        key = (_normalize_title(item.get("title", "")), _normalize_text_whitespace(item.get("date", "")))
        existed = best_by_key.get(key)
        if existed is None or _timeline_item_score(item) > _timeline_item_score(existed):
            best_by_key[key] = item

    return list(best_by_key.values())


def _merge_education_timeline(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        current = {
            "title": _pick_best_string(item.get("title")),
            "subtitle": _pick_best_string(item.get("subtitle")),
            "date": _pick_best_string(item.get("date")),
            "details": _ensure_string_list(item.get("details")),
        }
        if (
            merged
            and _looks_like_school_text(merged[-1].get("title", ""))
            and not merged[-1].get("subtitle")
            and not current.get("date")
            and not current.get("details")
            and _looks_like_major_text(current.get("title", ""))
        ):
            merged[-1]["subtitle"] = current.get("title", "")
            continue
        merged.append(current)
    return merged


def _merge_unique_strings(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for group in groups:
        for item in group:
            cleaned = _sanitize_numeric_artifacts(item)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            merged.append(cleaned)

    return merged


def _extract_name_from_filename(filename: str = "") -> str:
    base = re.sub(r"\.pdf$", "", filename or "", flags=re.I).strip()
    if not base:
        return ""

    split_by_keywords = re.split(r"(?:个人简历|简历|resume|cv|应聘|求职)", base, maxsplit=1, flags=re.I)[0]
    segments = [seg.strip() for seg in re.split(r"[_\-\s]+", split_by_keywords) if seg.strip()]
    candidates = [*segments, split_by_keywords]

    best = ""
    for candidate in candidates:
        chinese_parts = re.findall(r"[\u4e00-\u9fff]{2,4}", candidate)
        for part in chinese_parts:
            if any(stop in part for stop in NAME_STOPWORDS):
                continue
            best = part
    return _extract_name_core(best)


def _extract_name(markdown: str, filename: str) -> str:
    lines = [_clean_inline_text(line) for line in markdown.splitlines()]
    lines = [line for line in lines if line]

    for line in lines[:8]:
        if _is_standalone_section_title(line):
            continue
        if "resume" in line.lower():
            continue
        if any(stop in line for stop in ("简历", "个人简历", "curriculum vitae")):
            continue
        if "@" in line or re.search(r"\d{6,}", line) or _looks_like_date_range(line):
            continue
        if _looks_like_school_text(line):
            continue
        if _looks_like_major_text(line):
            continue
        if re.search(r"(?:专业|本科|硕士|博士|均分|主修|课程|CET|四级|六级)", line, re.I):
            continue
        if re.search(r"(公司|集团|科技|有限|实习|工程师|岗位|项目|社团|俱乐部|协会|成员|副社长|社长)", line):
            continue
        if len(line) > 80 or re.fullmatch(r"[\d\s\-_.]+", line):
            continue
        candidate = _extract_name_core(re.sub(r"[:?]+$", "", line))
        if candidate:
            return candidate

    filename_name = _extract_name_from_filename(filename)
    if filename_name:
        return filename_name
    return _extract_name_core(re.sub(r"\.pdf$", "", filename, flags=re.I))


def _build_structured_resume_rule_based(markdown_content: str, filename: str) -> dict[str, Any]:
    markdown_content = markdown_content or ""
    table_pairs = _extract_table_pairs(markdown_content)
    text_body = _strip_table_lines(markdown_content)
    sources = [source for source in [text_body, *_extract_table_column_texts(markdown_content)] if source]
    combined_text = "\n\n".join(source for source in sources if source)

    education_groups: list[list[dict[str, Any]]] = []
    work_groups: list[list[dict[str, Any]]] = []
    project_groups: list[list[dict[str, Any]]] = []
    skill_groups: list[list[str]] = []
    award_groups: list[list[str]] = []

    for source in sources:
        sections = _split_markdown_sections(source)
        education_groups.extend([_parse_timeline_section(section) for section in _find_sections(sections, "education")])
        work_groups.extend([_parse_timeline_section(section) for section in _find_sections(sections, "work")])
        project_groups.extend([_parse_timeline_section(section) for section in _find_sections(sections, "project")])
        skill_groups.extend([_parse_skill_section(section) for section in _find_sections(sections, "skills")])
        award_groups.extend([_parse_award_section(section) for section in _find_sections(sections, "awards")])

    basic_info = _extract_basic_info(combined_text, table_pairs=table_pairs)
    phone = _extract_phone(combined_text or markdown_content, table_pairs=table_pairs)
    if basic_info.get("wechat") and phone:
        wechat_digits = re.sub(r"\D+", "", basic_info.get("wechat", ""))
        phone_digits = re.sub(r"\D+", "", phone)
        if wechat_digits and phone_digits and wechat_digits == phone_digits:
            basic_info["wechat"] = ""
    education = _merge_duplicated_education(
        _repair_education_timeline(_merge_education_timeline(_merge_timeline_items(*education_groups)), combined_text or markdown_content)
    )

    if not education and any(basic_info.get(key) for key in ("school", "major", "degree", "grade")):
        education_details = []
        if basic_info.get("degree"):
            education_details.append(f"学历：{basic_info['degree']}")
        if basic_info.get("grade"):
            education_details.append(f"年级：{basic_info['grade']}")
        if basic_info.get("location"):
            education_details.append(f"所在地：{basic_info['location']}")

        education = [
            {
                "title": basic_info.get("school") or "教育信息",
                "subtitle": basic_info.get("major") or "",
                "date": "",
                "details": education_details,
            }
        ]

    work = _merge_timeline_items(*work_groups, _extract_contextual_timeline_items(combined_text or markdown_content, "work"))
    work, campus_experience = _split_work_and_campus(work)
    work = _cleanup_timeline_items(work)
    campus_experience = _cleanup_timeline_items(campus_experience)

    projects = _merge_timeline_items(*project_groups, _extract_contextual_timeline_items(combined_text or markdown_content, "project"))
    projects = _cleanup_project_items(_cleanup_timeline_items(projects))
    if not projects:
        projects = _extract_project_clues_from_text(combined_text or markdown_content)
    if not projects:
        projects = _derive_projects_from_timeline_items(work, campus_experience)
    if not campus_experience:
        campus_experience = _derive_campus_from_projects(projects)

    skills = _merge_unique_strings(*skill_groups)
    if not skills:
        skills = _extract_skills_from_text(combined_text or markdown_content)
    skills, skill_awards = _split_skills_and_awards(skills)

    awards = _dedupe_award_strings(_merge_unique_strings(*award_groups, skill_awards))
    if not awards:
        awards = _dedupe_award_strings(_merge_unique_strings(_extract_awards_from_text(combined_text or markdown_content), skill_awards))

    return {
        "name": _extract_name(combined_text or markdown_content, filename),
        "phone": phone,
        "email": _extract_email(combined_text or markdown_content, table_pairs=table_pairs),
        "basic_info": basic_info,
        "education": education,
        "work": work,
        "campus_experience": campus_experience,
        "projects": projects,
        "skills": skills,
        "awards": awards,
    }


def _normalize_basic_info(raw_basic: Any) -> dict[str, str]:
    basic = raw_basic if isinstance(raw_basic, dict) else {}
    normalized = {
        "name": _pick_best_string(basic.get("name")),
        "phone": _pick_best_string(basic.get("phone")),
        "email": _pick_best_string(basic.get("email")),
        "school": _pick_best_string(basic.get("school")),
        "major": _pick_best_string(basic.get("major")),
        "degree": _pick_best_string(basic.get("degree")),
        "grade": _pick_best_string(basic.get("grade")),
        "location": _pick_best_string(basic.get("location")),
        "intention": _pick_best_string(basic.get("intention")),
        "github": _pick_best_string(basic.get("github")),
        "wechat": _pick_best_string(basic.get("wechat")),
    }
    if normalized["wechat"] and normalized["phone"]:
        wechat_digits = re.sub(r"\D+", "", normalized["wechat"])
        phone_digits = re.sub(r"\D+", "", normalized["phone"])
        if wechat_digits and phone_digits and wechat_digits == phone_digits:
            normalized["wechat"] = ""
    return normalized


def _normalize_education_items(raw_items: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    education: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        school = _pick_best_string(item.get("school"), item.get("title"), item.get("name"))
        major = _pick_best_string(item.get("major"), item.get("subtitle"))
        date_field = _pick_best_string(item.get("date"))
        details = _ensure_string_list(item.get("details"))
        if not school:
            school = (
                _extract_school_from_text(date_field)
                or next((_extract_school_from_text(line) for line in details if _extract_school_from_text(line)), "")
            )
        if not major:
            major = (
                _extract_major_from_text(date_field)
                or _extract_major_from_text(school)
                or next((_extract_major_from_text(line) for line in details if _extract_major_from_text(line)), "")
            )
        education.append(
            {
                "school": school,
                "major": major,
                "degree": _pick_best_string(item.get("degree")),
                "start_time": _normalize_month(_pick_best_string(item.get("start_time"), item.get("start"))),
                "end_time": _normalize_month(_pick_best_string(item.get("end_time"), item.get("end"))),
            }
        )

    return [item for item in education if any(item.values())]


def _normalize_experience_items(raw_items: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    experience: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        descriptions = _ensure_string_list(item.get("description"))
        if not descriptions:
            descriptions = _ensure_string_list(item.get("details"))

        experience.append(
            {
                "company": _pick_best_string(item.get("company"), item.get("title"), item.get("name")),
                "role": _pick_best_string(item.get("role"), item.get("position"), item.get("subtitle")),
                "start_time": _normalize_month(_pick_best_string(item.get("start_time"), item.get("start"))),
                "end_time": _normalize_month(_pick_best_string(item.get("end_time"), item.get("end"))),
                "description": descriptions,
            }
        )
    return [item for item in experience if any(item.values())]


def _normalize_project_items(raw_items: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(raw_items, list):
        return [], []

    projects: list[dict[str, Any]] = []
    project_skills: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        name = _pick_best_string(item.get("name"), item.get("title"), item.get("project_name"))
        role = _pick_best_string(item.get("role"), item.get("position"), item.get("subtitle"))
        start_time = _normalize_month(_pick_best_string(item.get("start_time"), item.get("start")))
        end_time = _normalize_month(_pick_best_string(item.get("end_time"), item.get("end")))
        details = _ensure_string_list(item.get("description"))
        if not details:
            details = _ensure_string_list(item.get("details"))

        tech_stack = _ensure_string_list(item.get("tech_stack"))
        if not tech_stack:
            tech_stack = _ensure_string_list(item.get("technologies"))
        if tech_stack:
            details = [f"技术栈: {', '.join(tech_stack)}", *details]
            project_skills.extend(tech_stack)

        projects.append(
            {
                "title": name,
                "subtitle": role,
                "date": _parse_date_span(start_time, end_time),
                "details": details,
            }
        )
    return [item for item in projects if any(item.values())], _merge_skills(project_skills)


def _normalize_awards(raw_items: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    awards: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, str):
            title = _normalize_text_whitespace(item)
            if title:
                awards.append({"title": title, "description": "", "time": ""})
            continue
        if not isinstance(item, dict):
            continue
        awards.append(
            {
                "title": _pick_best_string(item.get("title"), item.get("name")),
                "description": _pick_best_string(item.get("description"), item.get("detail")),
                "time": _normalize_month(_pick_best_string(item.get("time"), item.get("date"))),
            }
        )
    deduped: list[dict[str, Any]] = []
    for item in awards:
        if not any(item.values()):
            continue
        title = _pick_best_string(item.get("title"))
        if not title:
            continue
        key = _normalize_award_compare_text(title)
        if not key:
            continue
        replaced = False
        for index, existing in enumerate(deduped):
            existing_key = _normalize_award_compare_text(existing.get("title", ""))
            if key == existing_key or key in existing_key or existing_key in key:
                if len(title) > len(existing.get("title", "")):
                    deduped[index] = item
                replaced = True
                break
        if not replaced:
            deduped.append(item)
    return deduped


async def _extract_structured_resume_with_llm(markdown_content: str, filename: str) -> dict[str, Any] | None:
    global RESUME_LLM_DISABLED, RESUME_LLM_DISABLED_UNTIL

    now = time.time()
    if RESUME_LLM_DISABLED:
        if now < RESUME_LLM_DISABLED_UNTIL:
            return None
        RESUME_LLM_DISABLED = False
        RESUME_LLM_DISABLED_UNTIL = 0.0

    text = (markdown_content or "").strip()
    if not text:
        return None

    clipped = text[:RESUME_LLM_MAX_CHARS]
    prompt = (
        "请从下面的简历文本中提取结构化信息，并且只返回 JSON。"
        "不要返回任何解释性文字。"
        "JSON schema:\n"
        "{\n"
        '  "name": "string",\n'
        '  "phone": "string",\n'
        '  "email": "string",\n'
        '  "basic_info": {"school":"string","major":"string","degree":"string","grade":"string","location":"string","intention":"string","github":"string","wechat":"string"},\n'
        '  "education": [{"school":"string","major":"string","degree":"string","start_time":"string","end_time":"string"}],\n'
        '  "experience": [{"company":"string","role":"string","start_time":"string","end_time":"string","description":["string"]}],\n'
        '  "campus_experience": [{"company":"string","role":"string","start_time":"string","end_time":"string","description":["string"]}],\n'
        '  "projects": [{"name":"string","role":"string","start_time":"string","end_time":"string","tech_stack":["string"],"description":["string"]}],\n'
        '  "skills": ["string"],\n'
        '  "awards": [{"title":"string","description":"string","time":"string"}]\n'
        "}\n"
        f"文件名: {filename}\n"
        "简历正文如下:\n"
        f"{clipped}"
    )

    try:
        model = select_model()
        response = await model.call([{"role": "user", "content": prompt}], stream=False)
        parsed = _extract_json_object(_model_message_to_text(response))
        if not parsed:
            return None
    except Exception as exc:
        RESUME_LLM_DISABLED = True
        RESUME_LLM_DISABLED_UNTIL = time.time() + RESUME_LLM_RETRY_COOLDOWN_SECONDS
        logger.warning(
            "Temporarily disable LLM structured extraction for %ss due to upstream error: %s",
            RESUME_LLM_RETRY_COOLDOWN_SECONDS,
            exc,
        )
        return None

    basic_info = _normalize_basic_info(parsed.get("basic_info"))
    education = _normalize_education_items(parsed.get("education"))
    experience = _normalize_experience_items(parsed.get("experience") or parsed.get("work"))
    campus_experience = _normalize_experience_items(parsed.get("campus_experience"))
    projects, project_skills = _normalize_project_items(parsed.get("projects") or parsed.get("project"))
    awards = _normalize_awards(parsed.get("awards"))
    skills = _merge_skills(_ensure_string_list(parsed.get("skills")), project_skills)

    work = [
        {
            "title": item.get("company", ""),
            "subtitle": item.get("role", ""),
            "date": _parse_date_span(item.get("start_time", ""), item.get("end_time", "")),
            "details": _ensure_string_list(item.get("description")),
        }
        for item in experience
    ]
    campus_work = [
        {
            "title": item.get("company", ""),
            "subtitle": item.get("role", ""),
            "date": _parse_date_span(item.get("start_time", ""), item.get("end_time", "")),
            "details": _ensure_string_list(item.get("description")),
        }
        for item in campus_experience
    ]

    return {
        "name": _pick_best_string(parsed.get("name"), basic_info.get("name")),
        "phone": _pick_best_string(parsed.get("phone"), basic_info.get("phone")),
        "email": _pick_best_string(parsed.get("email"), basic_info.get("email")),
        "basic_info": basic_info,
        "education": education,
        "experience": experience,
        "work": [item for item in work if any(item.values())],
        "campus_experience": [item for item in campus_work if any(item.values())],
        "projects": projects,
        "skills": skills,
        "awards": awards,
    }


async def _build_structured_resume(markdown_content: str, filename: str) -> dict[str, Any]:
    rule_data = _build_structured_resume_rule_based(markdown_content, filename)
    llm_data = await _extract_structured_resume_with_llm(markdown_content, filename)

    rule_experience = _build_rule_based_experience(rule_data.get("work", []))

    if not llm_data:
        rule_basic = dict(rule_data.get("basic_info") or {})
        rule_basic["name"] = _extract_name_core(_pick_best_string(rule_data.get("name")))
        rule_basic["phone"] = _pick_best_string(rule_data.get("phone"))
        rule_basic["email"] = _pick_best_string(rule_data.get("email"))
        return {
            **rule_data,
            "basic_info": rule_basic,
            "experience": rule_experience,
        }

    llm_basic = dict(llm_data.get("basic_info") or {})
    rule_basic = dict(rule_data.get("basic_info") or {})
    basic_info = {
        "name": _extract_name_core(_pick_best_string(llm_data.get("name"), rule_data.get("name"), llm_basic.get("name"))),
        "phone": _pick_best_string(llm_data.get("phone"), rule_data.get("phone"), llm_basic.get("phone")),
        "email": _pick_best_string(llm_data.get("email"), rule_data.get("email"), llm_basic.get("email")),
        "school": _pick_best_string(llm_basic.get("school"), rule_basic.get("school")),
        "major": _pick_best_string(llm_basic.get("major"), rule_basic.get("major")),
        "degree": _pick_best_string(llm_basic.get("degree"), rule_basic.get("degree")),
        "grade": _pick_best_string(llm_basic.get("grade"), rule_basic.get("grade")),
        "location": _pick_best_string(llm_basic.get("location"), rule_basic.get("location")),
        "intention": _pick_best_string(llm_basic.get("intention"), rule_basic.get("intention")),
        "github": _pick_best_string(llm_basic.get("github"), rule_basic.get("github")),
        "wechat": _pick_best_string(llm_basic.get("wechat"), rule_basic.get("wechat")),
    }
    basic_info["intention"] = re.split(r"(?:工作年限)\s*[:：]?", basic_info["intention"], maxsplit=1)[0].strip()
    if basic_info["wechat"] and basic_info["phone"]:
        wechat_digits = re.sub(r"\D+", "", basic_info["wechat"])
        phone_digits = re.sub(r"\D+", "", basic_info["phone"])
        if wechat_digits and phone_digits and wechat_digits == phone_digits:
            basic_info["wechat"] = ""

    education = llm_data.get("education") or rule_data.get("education") or []
    if not llm_data.get("education"):
        education = _merge_duplicated_education(_repair_education_timeline(education, markdown_content))
    experience = llm_data.get("experience") or rule_experience
    work = llm_data.get("work") or rule_data.get("work") or []
    projects = llm_data.get("projects") or rule_data.get("projects") or []
    awards = llm_data.get("awards") or rule_data.get("awards") or []
    skills = _merge_skills(llm_data.get("skills") or [], rule_data.get("skills") or [])
    campus_experience = llm_data.get("campus_experience") or rule_data.get("campus_experience") or []
    if not campus_experience:
        work, campus_experience = _split_work_and_campus(work)
    work = _cleanup_timeline_items(work)
    campus_experience = _cleanup_timeline_items(campus_experience)
    projects = _cleanup_project_items(_cleanup_timeline_items(projects))

    if experience:
        normalized_work_items = [
            {
                "title": item.get("company", ""),
                "subtitle": item.get("role", ""),
                "date": _parse_date_span(item.get("start_time", ""), item.get("end_time", "")),
                "details": _ensure_string_list(item.get("description")),
            }
            for item in experience
        ]
        normalized_work_items = [item for item in normalized_work_items if any(item.values())]
        work, experience_campus = _split_work_and_campus(normalized_work_items)
        campus_experience = _merge_timeline_items(campus_experience, experience_campus)
        work = _cleanup_timeline_items(work)
        campus_experience = _cleanup_timeline_items(campus_experience)
        experience = _build_rule_based_experience(work)
    if not projects:
        projects = _derive_projects_from_timeline_items(work, campus_experience)
    projects = _cleanup_project_items(projects)
    if not campus_experience:
        campus_experience = _derive_campus_from_projects(projects)
    skills, skill_awards = _split_skills_and_awards(skills)
    if skill_awards:
        awards = _normalize_awards([*(awards or []), *skill_awards])

    return {
        "name": basic_info["name"],
        "phone": basic_info["phone"],
        "email": basic_info["email"],
        "basic_info": basic_info,
        "education": education,
        "experience": experience,
        "work": work,
        "campus_experience": campus_experience,
        "projects": projects,
        "skills": skills,
        "awards": awards,
    }


async def _serialize_resume(resume_record: UserResume, include_markdown: bool = True) -> dict[str, Any]:
    data = resume_record.to_dict(include_markdown=include_markdown)
    cache_key = f"{RESUME_STRUCTURED_CACHE_VERSION}:{resume_record.content_hash}:{resume_record.filename}"
    structured_resume = RESUME_STRUCTURED_CACHE.get(cache_key)
    if structured_resume is None:
        structured_resume = await _build_structured_resume(resume_record.markdown_content or "", resume_record.filename)
        RESUME_STRUCTURED_CACHE[cache_key] = structured_resume
        while len(RESUME_STRUCTURED_CACHE) > RESUME_STRUCTURED_CACHE_MAX_ITEMS:
            RESUME_STRUCTURED_CACHE.pop(next(iter(RESUME_STRUCTURED_CACHE)))

    data["structured_resume"] = structured_resume
    return data


@resume.get("")
async def get_my_resumes(current_user: User = Depends(get_required_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserResume).where(UserResume.user_id == current_user.id).order_by(UserResume.created_at.desc(), UserResume.id.desc())
    )
    resume_records = result.scalars().all()
    return {
        "message": "success",
        "resumes": [resume_record.to_dict(include_markdown=False) for resume_record in resume_records],
    }


@resume.get("/{resume_id}")
async def get_my_resume_detail(
    resume_id: int,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserResume).where(
            UserResume.id == resume_id,
            UserResume.user_id == current_user.id,
        )
    )
    resume_record = result.scalar_one_or_none()
    if resume_record is None:
        raise HTTPException(status_code=404, detail="简历不存在")

    return {
        "message": "success",
        "resume": await _serialize_resume(resume_record),
    }


@resume.post("")
async def upload_my_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择 PDF 简历文件")

    filename = Path(file.filename).name
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="仅支持上传 PDF 简历")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="上传的简历文件为空")

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        content_hash = await calculate_content_hash(file_bytes)
        db_id = f"user_resume_{current_user.id}_{uuid.uuid4().hex[:8]}"

        native_task = process_file_to_markdown(
            temp_path,
            params={
                "enable_ocr": "disable",
                "db_id": db_id,
            },
        )
        ocr_task = process_file_to_markdown(
            temp_path,
            params={
                "enable_ocr": "mineru_official",
                "db_id": db_id,
            },
        )
        native_result, ocr_result = await asyncio.gather(native_task, ocr_task, return_exceptions=True)

        candidates: list[tuple[str, str]] = []
        if isinstance(native_result, str) and native_result.strip():
            candidates.append(("native_pdf_text", native_result))
        if isinstance(ocr_result, str) and ocr_result.strip():
            candidates.append(("mineru_official", ocr_result))

        if not candidates:
            if isinstance(ocr_result, Exception):
                raise ocr_result
            if isinstance(native_result, Exception):
                raise native_result
            raise DocumentProcessorException("无法从该 PDF 提取有效文本", "resume_parser", "no_content")

        score_map = {name: round(_text_quality_score(text), 2) for name, text in candidates}
        selected_parser, markdown_content = _select_best_markdown(candidates)
        logger.info(
            "Resume parser selected for user %s: %s (scores=%s)",
            current_user.user_id,
            selected_parser,
            score_map,
        )
        parser_name = f"hybrid:{selected_parser}"

        object_name = f"{current_user.user_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
        file_url = await aupload_file_to_minio("user-resumes", object_name, file_bytes, "pdf")

        resume_record = UserResume(
            user_id=current_user.id,
            filename=filename,
            content_hash=content_hash,
            file_size=len(file_bytes),
            bucket_name="user-resumes",
            object_name=object_name,
            file_url=file_url,
            parser_name=parser_name,
            markdown_content=markdown_content,
        )
        db.add(resume_record)

        await db.commit()
        await db.refresh(resume_record)

        if openviking_service.is_enabled():
            try:
                await openviking_service.sync_resume(resume_record)
                await openviking_service.sync_resume_memory(resume_record)
            except Exception as exc:
                logger.warning("Sync resume to OpenViking failed for user %s: %s", current_user.user_id, exc)

        return {
            "message": "success",
            "resume": await _serialize_resume(resume_record),
        }
    except DocumentProcessorException as exc:
        logger.error(f"Resume parsing failed for user {current_user.user_id}: {exc}")
        raise HTTPException(status_code=502, detail=f"简历解析失败：{exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Resume upload failed for user {current_user.user_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"简历上传失败：{exc}") from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@resume.delete("/{resume_id}")
async def delete_my_resume(
    resume_id: int,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserResume).where(
            UserResume.id == resume_id,
            UserResume.user_id == current_user.id,
        )
    )
    resume_record = result.scalar_one_or_none()
    if resume_record is None:
        raise HTTPException(status_code=404, detail="简历不存在")

    try:
        minio_client = get_minio_client()
        await minio_client.adelete_file(resume_record.bucket_name, resume_record.object_name)

        if openviking_service.is_enabled():
            try:
                await openviking_service.remove_resume(resume_record)
                await openviking_service.remove_resume_memory(resume_record)
            except Exception as exc:
                logger.warning("Remove resume from OpenViking failed for user %s: %s", current_user.user_id, exc)

        cache_key = f"{RESUME_STRUCTURED_CACHE_VERSION}:{resume_record.content_hash}:{resume_record.filename}"
        RESUME_STRUCTURED_CACHE.pop(cache_key, None)

        await db.delete(resume_record)
        await db.commit()
        return {"message": "success"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Resume delete failed for user {current_user.user_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"删除简历失败：{exc}") from exc


