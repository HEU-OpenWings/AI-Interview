"""简历结构化摘要服务 - 优先使用 LLM，并提供本地规则降级。"""

import asyncio
import json
import re
from typing import Any

from src.agents.common.models import load_chat_model
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import UserResume
from src.utils import logger
from src.utils.prompts import resume_extraction_prompt

# LLM 调用重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒
LLM_TIMEOUT = 120  # 秒

# 默认使用可靠模型进行摘要提取
DEFAULT_SUMMARY_MODEL = "siliconflow/Pro/deepseek-ai/DeepSeek-V3.2"

_LOCAL_SKILL_PATTERNS = (
    (r"(?<![A-Za-z0-9_])python(?![A-Za-z0-9_])", "Python"),
    (r"(?<![A-Za-z0-9_])java(?![A-Za-z0-9_])", "Java"),
    (r"(?<![A-Za-z0-9_])javascript(?![A-Za-z0-9_])", "JavaScript"),
    (r"(?<![A-Za-z0-9_])typescript(?![A-Za-z0-9_])", "TypeScript"),
    (r"(?<![A-Za-z0-9_])c\+\+(?![A-Za-z0-9_])", "C++"),
    (r"(?<![A-Za-z0-9_])c#(?![A-Za-z0-9_])", "C#"),
    (r"(?<![A-Za-z0-9_])(?:go|golang)(?![A-Za-z0-9_])", "Go"),
    (r"(?<![A-Za-z0-9_])rust(?![A-Za-z0-9_])", "Rust"),
    (r"(?<![A-Za-z0-9_])fastapi(?![A-Za-z0-9_])", "FastAPI"),
    (r"(?<![A-Za-z0-9_])django(?![A-Za-z0-9_])", "Django"),
    (r"(?<![A-Za-z0-9_])flask(?![A-Za-z0-9_])", "Flask"),
    (r"(?<![A-Za-z0-9_])spring\s*boot(?![A-Za-z0-9_])", "Spring Boot"),
    (r"(?<![A-Za-z0-9_])node(?:\.js|js)(?![A-Za-z0-9_])", "Node.js"),
    (r"(?<![A-Za-z0-9_])react(?:\.js|js)?(?![A-Za-z0-9_])", "React"),
    (r"(?<![A-Za-z0-9_])vue(?:\.js|js)?(?![A-Za-z0-9_])", "Vue"),
    (r"(?<![A-Za-z0-9_])sql(?![A-Za-z0-9_])", "SQL"),
    (r"(?<![A-Za-z0-9_])mysql(?![A-Za-z0-9_])", "MySQL"),
    (r"(?<![A-Za-z0-9_])postgresql(?![A-Za-z0-9_])", "PostgreSQL"),
    (r"(?<![A-Za-z0-9_])mongodb(?![A-Za-z0-9_])", "MongoDB"),
    (r"(?<![A-Za-z0-9_])redis(?![A-Za-z0-9_])", "Redis"),
    (r"(?<![A-Za-z0-9_])docker(?![A-Za-z0-9_])", "Docker"),
    (r"(?<![A-Za-z0-9_])(?:kubernetes|k8s)(?![A-Za-z0-9_])", "Kubernetes"),
    (r"(?<![A-Za-z0-9_])linux(?![A-Za-z0-9_])", "Linux"),
    (r"(?<![A-Za-z0-9_])git(?![A-Za-z0-9_])", "Git"),
    (r"(?<![A-Za-z0-9_])pytorch(?![A-Za-z0-9_])", "PyTorch"),
    (r"(?<![A-Za-z0-9_])tensorflow(?![A-Za-z0-9_])", "TensorFlow"),
    (r"机器学习|(?<![A-Za-z0-9_])machine\s+learning(?![A-Za-z0-9_])", "机器学习"),
    (r"深度学习|(?<![A-Za-z0-9_])deep\s+learning(?![A-Za-z0-9_])", "深度学习"),
    (r"自然语言处理|(?<![A-Za-z0-9_])nlp(?![A-Za-z0-9_])", "自然语言处理"),
    (r"计算机视觉|(?<![A-Za-z0-9_])computer\s+vision(?![A-Za-z0-9_])", "计算机视觉"),
    (r"大语言模型|大模型|(?<![A-Za-z0-9_])llm(?![A-Za-z0-9_])", "大语言模型"),
)


class ResumeSummaryService:
    """简历结构化摘要服务"""

    def __init__(self, model_name: str = DEFAULT_SUMMARY_MODEL) -> None:
        self.model_name = model_name

    async def extract_summary(self, markdown_content: str) -> dict[str, Any]:
        """
        调用 LLM 提取简历结构化信息，支持重试、超时和本地规则降级。

        Args:
            markdown_content: 简历的 markdown 内容

        Returns:
            提取的结构化字典

        Raises:
            ValueError: 简历内容为空
        """
        if not markdown_content or not markdown_content.strip():
            raise ValueError("简历内容为空，无法提取摘要")

        try:
            model = load_chat_model(self.model_name)
        except Exception as e:
            logger.warning(f"LLM 模型初始化失败，使用本地规则提取简历摘要: {e}")
            return self._extract_local_summary(markdown_content)

        prompt = resume_extraction_prompt.replace("{resume_text}", markdown_content)

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"LLM 提取尝试 {attempt}/{MAX_RETRIES}")
            try:
                response = await asyncio.wait_for(model.ainvoke(prompt), timeout=LLM_TIMEOUT)
            except TimeoutError:
                last_error = f"LLM 调用超时（{LLM_TIMEOUT}s）"
                logger.warning(f"第 {attempt} 次 LLM 调用超时")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                continue
            except (ConnectionError, OSError) as e:
                last_error = str(e)
                logger.warning(f"第 {attempt} 次 LLM 网络错误: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                continue
            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM 调用失败，使用本地规则提取简历摘要: {e}")
                break

            content = response.content if hasattr(response, "content") else str(response)

            logger.debug(f"LLM 原始响应长度: {len(content)} 字符")
            logger.debug(f"LLM 完整响应: {content}")

            # 尝试多种方式解析 JSON
            summary = self._parse_json_response(content)
            if summary:
                logger.info("简历摘要提取成功")
                return summary

            # JSON 解析失败，LLM 已返回内容，重试可能得到不同结果
            last_error = "JSON 解析失败"
            logger.warning(f"第 {attempt} 次 JSON 解析失败，原始响应: {content[:500]}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)

        logger.warning(f"LLM 简历摘要提取不可用，切换到本地规则: {last_error}")
        return self._extract_local_summary(markdown_content)

    @staticmethod
    def _extract_labeled_value(content: str, labels: tuple[str, ...]) -> str | None:
        """提取形如“标签：值”的单行字段，仅处理显式信息。"""
        for raw_line in content.splitlines():
            line = re.sub(r"^[\s>#*\-]+", "", raw_line).replace("**", "").replace("__", "").strip()
            for label in labels:
                match = re.match(rf"{re.escape(label)}\s*[:：]\s*(.+)$", line, re.IGNORECASE)
                if match:
                    value = match.group(1).strip().strip("`*_ ")
                    return value or None
        return None

    @staticmethod
    def _dedupe_values(values: list[str]) -> list[str]:
        """按出现顺序去重，比较时忽略大小写。"""
        result = []
        seen = set()
        for value in values:
            cleaned = value.strip()
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result

    def _extract_labeled_list(self, content: str, labels: tuple[str, ...]) -> list[str]:
        """提取逗号、顿号或分号分隔的显式列表字段。"""
        value = self._extract_labeled_value(content, labels)
        if not value:
            return []

        items = []
        for item in re.split(r"[,，、;；|]+", value):
            cleaned = re.sub(r"^(?:熟练掌握|熟悉|掌握|了解|精通|使用|运用)\s*", "", item.strip())
            if cleaned:
                items.append(cleaned)
        return self._dedupe_values(items)

    @staticmethod
    def _extract_url(content: str, host_pattern: str) -> str | None:
        match = re.search(rf"https?://(?:www\.)?{host_pattern}/[^\s)>\]]+", content, re.IGNORECASE)
        return match.group(0).rstrip(".,;，。；") if match else None

    def _extract_local_summary(self, markdown_content: str) -> dict[str, Any]:
        """在 LLM 不可用时，从明确文本和高置信度关键词生成兼容摘要。"""
        name = self._extract_labeled_value(markdown_content, ("姓名", "Name"))
        gender = self._extract_labeled_value(markdown_content, ("性别", "Gender"))
        age_text = self._extract_labeled_value(markdown_content, ("年龄", "Age"))
        age_match = re.search(r"\d{1,3}", age_text or "")
        age = int(age_match.group(0)) if age_match else None

        phone_match = re.search(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)", markdown_content)
        email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", markdown_content, re.IGNORECASE)

        technical = self._extract_labeled_list(markdown_content, ("专业技能", "技术技能", "技能", "技术栈"))
        for pattern, canonical_name in _LOCAL_SKILL_PATTERNS:
            if re.search(pattern, markdown_content, re.IGNORECASE):
                technical.append(canonical_name)
        technical = self._dedupe_values(technical)

        photo_value = self._extract_labeled_value(markdown_content, ("照片", "证件照", "Photo"))
        photo_match = re.search(r"https?://[^\s)>\]]+", photo_value or "", re.IGNORECASE)

        summary = {
            "basic_info": {
                "name": name,
                "gender": gender,
                "age": age,
                "phone": phone_match.group(0) if phone_match else None,
                "email": email_match.group(0) if email_match else None,
                "location": self._extract_labeled_value(markdown_content, ("所在地", "现居地", "Location")),
                "github": self._extract_url(markdown_content, r"github\.com"),
                "linkedin": self._extract_url(markdown_content, r"linkedin\.com"),
                "photo_url": photo_match.group(0).rstrip(".,;，。；") if photo_match else None,
            },
            "education": [],
            "work_experience": [],
            "project_experience": [],
            "skills": {
                "technical": technical,
                "languages": self._extract_labeled_list(markdown_content, ("语言能力", "语言", "Languages")),
                "certifications": self._extract_labeled_list(markdown_content, ("证书", "资质", "Certifications")),
            },
            "awards": self._extract_labeled_list(markdown_content, ("获奖情况", "荣誉", "Awards")),
            "training": self._extract_labeled_list(markdown_content, ("培训经历", "培训", "Training")),
            "self_evaluation": self._extract_labeled_value(markdown_content, ("自我评价", "Self Evaluation")),
            "job_preference": {
                "job_intention": self._extract_labeled_value(
                    markdown_content, ("求职意向", "目标岗位", "意向岗位", "Job Intention")
                ),
                "expected_salary": self._extract_labeled_value(markdown_content, ("期望薪资", "Expected Salary")),
                "desired_location": self._extract_labeled_value(
                    markdown_content, ("期望工作地点", "期望地点", "Desired Location")
                ),
            },
        }

        logger.info(f"使用本地规则生成简历摘要，提取到 {len(technical)} 项技术技能")
        return summary

    def _preprocess_json_text(self, text: str) -> str:
        """
        预处理 JSON 文本，修复常见问题。
        """
        # 修复 LaTeX 公式残留（如 $10 \$ → 10%）
        text = re.sub(r"\$+([^$]*)\$+", lambda m: self._decode_latex_fragment(m.group(1)), text)

        # 修复换行符问题
        text = text.replace("\\n", "\n").replace("\n", " ")

        # 移除多余的控制字符
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

        return text

    def _decode_latex_fragment(self, latex: str) -> str:
        """
        解码 LaTeX 公式片段为正常文本。
        """
        if not latex:
            return ""

        # 百分比，如 10\% 或 10 % → 10%
        latex = re.sub(r"(\d+)\s*\\?%", r"\1%", latex)
        # 上标数字，如 ^ { 20 + } → 20+
        latex = re.sub(r"\^\s*\{\s*([\d\s\+]+)\s*\}", r"\1", latex)
        # 移除 \left \right 等 LaTeX 命令
        latex = re.sub(r"\\[a-zA-Z]+\s*", "", latex)
        # 清理多余空格
        latex = re.sub(r"\s+", " ", latex).strip()

        return latex

    @staticmethod
    def _as_json_object(value: Any) -> dict[str, Any] | None:
        """Return parsed JSON only when its top-level value is an object."""
        return value if isinstance(value, dict) else None

    def _parse_json_response(self, content: str) -> dict[str, Any] | None:
        """
        解析 LLM 返回的内容，尝试提取 JSON。

        支持多种格式：
        1. 直接是 JSON 对象
        2. markdown 代码块包裹的 JSON
        3. JSON 字符串
        4. 不完整 JSON 的容错解析
        """
        if not content:
            return None

        # 去除首尾空白
        content = content.strip()

        # 尝试 1: 直接解析（最常见情况）
        try:
            return self._as_json_object(json.loads(content))
        except json.JSONDecodeError:
            pass

        # 尝试 2: 提取 markdown 代码块中的 JSON
        json_block_patterns = [
            r"```json\s*([\s\S]*?)\s*```",
            r"```\s*([\s\S]*?)\s*```",
        ]
        for pattern in json_block_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                json_str = match.group(1).strip()
                try:
                    return self._as_json_object(json.loads(json_str))
                except json.JSONDecodeError:
                    continue

        # 尝试 3: 预处理后解析（修复 LaTeX 等问题）
        try:
            cleaned = self._preprocess_json_text(content)
            return self._as_json_object(json.loads(cleaned))
        except json.JSONDecodeError:
            pass

        # 尝试 4: 查找 JSON 对象模式
        json_pattern = r"\{[\s\S]*\}"
        match = re.search(json_pattern, content)
        if match:
            json_str = match.group(0)
            try:
                return self._as_json_object(json.loads(json_str))
            except json.JSONDecodeError:
                pass

            # 尝试修复常见的 JSON 问题
            try:
                fixed = self._fix_common_json_errors(json_str)
                return self._as_json_object(json.loads(fixed))
            except json.JSONDecodeError:
                pass

        # 尝试 5: 容错解析 - 查找关键字段后截取
        try:
            result = self._fallback_parse(content)
            if result:
                return result
        except Exception:
            pass

        return None

    def _fix_common_json_errors(self, json_str: str) -> str:
        """
        修复常见的 JSON 语法错误。
        """
        # 移除尾部逗号
        json_str = re.sub(r",(\s*[\]})])", r"\1", json_str)

        # 修复单引号为双引号（简单情况）
        # 注意：这个修复比较危险，禁用
        # json_str = re.sub(r"'([^']*)'", r'"\1"', json_str)

        # 移除 JavaScript 注释
        json_str = re.sub(r"//.*?$", "", json_str, flags=re.MULTILINE)

        # 修复 LaTeX 百分号
        json_str = re.sub(r"(\\?)%+", "%", json_str)

        # 修复换行
        json_str = re.sub(r"\\n", " ", json_str)

        return json_str

    def _fallback_parse(self, content: str) -> dict[str, Any] | None:
        """
        容错解析：从内容中提取已知的 JSON 字段。
        用于处理 LLM 返回不完整 JSON 的情况。
        """
        # 提取最外层的大括号内容
        first_brace = content.find("{")
        last_brace = content.rfind("}")

        if first_brace == -1 or last_brace == -1 or first_brace >= last_brace:
            return None

        truncated = content[first_brace : last_brace + 1]

        # 尝试解析
        try:
            return self._as_json_object(json.loads(truncated))
        except json.JSONDecodeError:
            pass

        # 尝试修复后解析
        fixed = self._fix_common_json_errors(truncated)
        try:
            return self._as_json_object(json.loads(fixed))
        except json.JSONDecodeError:
            pass

        # 尝试逐个字段解析
        result = {}
        field_patterns = {
            "basic_info": r'"basic_info"\s*:\s*(\{[^}]*\})',
            "education": r'"education"\s*:\s*(\[[^\]]*\])',
            "work_experience": r'"work_experience"\s*:\s*(\[[^\]]*\])',
            "project_experience": r'"project_experience"\s*:\s*(\[[^\]]*\])',
            "skills": r'"skills"\s*:\s*(\{[^}]*\})',
            "awards": r'"awards"\s*:\s*(\[[^\]]*\])',
        }

        for field, pattern in field_patterns.items():
            match = re.search(pattern, content, re.DOTALL)
            if match:
                try:
                    result[field] = json.loads(match.group(1))
                except json.JSONDecodeError:
                    # 尝试修复
                    fixed_field = self._fix_common_json_errors(match.group(1))
                    try:
                        result[field] = json.loads(fixed_field)
                    except json.JSONDecodeError:
                        pass

        if result:
            logger.info(f"使用容错解析提取了 {len(result)} 个字段")
            return result

        return None

    async def update_resume_summary(self, resume_id: int) -> bool:
        """
        更新指定简历的摘要信息。

        Args:
            resume_id: 简历记录 ID

        Returns:
            是否更新成功
        """
        async with pg_manager.get_async_session_context() as session:
            from sqlalchemy import select

            result = await session.execute(select(UserResume).where(UserResume.id == resume_id))
            resume = result.scalar_one_or_none()

            if not resume:
                logger.warning(f"简历不存在，ID: {resume_id}")
                return False

            # 更新状态为处理中
            resume.summary_status = "processing"
            await session.commit()

            try:
                markdown_content = resume.markdown_content or ""
                if not markdown_content.strip():
                    logger.warning(f"简历 markdown_content 为空，跳过提取，resume_id={resume_id}")
                    resume.summary_status = "failed"
                    resume.summary_error = "PDF 解析结果为空，无法提取摘要"
                    await session.commit()
                    return False

                summary = await self.extract_summary(markdown_content)

                if summary:
                    resume.summary_json = summary
                    resume.summary_status = "completed"
                    resume.summary_error = None

                    # 回填意向岗位
                    detected = summary.get("job_preference", {}).get("job_intention", "")
                    if detected and not resume.detected_position:
                        resume.detected_position = detected

                    logger.info(f"简历摘要更新成功，ID: {resume_id}")
                else:
                    resume.summary_status = "failed"
                    resume.summary_error = "LLM 提取返回空结果"
                    logger.warning(f"简历摘要提取返回空，ID: {resume_id}")

                await session.commit()
                return True

            except Exception as e:
                logger.error(f"更新简历摘要失败，ID: {resume_id}, 错误: {e}")
                resume.summary_status = "failed"
                resume.summary_error = str(e)
                await session.commit()
                return False


# 全局单例
resume_summary_service = ResumeSummaryService()
