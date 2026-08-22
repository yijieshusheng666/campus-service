"""LLM 封装层：支持 OpenAI 兼容 API 与 Ollama(ChatOllama)。

- 提取模式：ChatPromptTemplate | LLM | StrOutputParser，返回结构化简历字段。
- 兼容：base_url 指向 Ollama 的 /v1 时，langchain_openai 也可以直连；
  也可直接使用 langchain_ollama.ChatOllama（本地）。由配置决定。
"""
import json
import logging
import re
from functools import lru_cache

from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.config import settings

logger = logging.getLogger(__name__)

# 云 API 单次请求超时（秒）：过长会拖慢整体流程，缩短快速失败
LLM_REQ_TIMEOUT = 120


@lru_cache(maxsize=1)
def _build_llm():
    """构建并复用同一个 LLM 客户端实例。

    进程内只创建一次，携带连接池与 keep-alive，避免每次调用反复握手建连，
    从而显著降低多次 AI 请求的往返延迟，且不影响传给 LLM 的任何内容。
    """
    base_url = settings.LLM_BASE_URL.rstrip("/")
    lower_base = base_url.lower()
    api_key = (settings.LLM_API_KEY or "").strip()
    uses_local_ollama = (
        "ollama" in lower_base
        or "11434" in lower_base
        or not api_key
        or api_key.lower() == "ollama"
    )
    if uses_local_ollama:
        # 本地 Ollama：走 ChatOllama
        from langchain_ollama import ChatOllama
        host = settings.OLLAMA_HOST.rstrip("/")
        logger.info("使用 ChatOllama，model=%s, host=%s", settings.LLM_MODEL, host)
        return ChatOllama(
            model=settings.LLM_MODEL,
            base_url=host,
            temperature=settings.LLM_TEMPERATURE,
            num_predict=settings.LLM_MAX_TOKENS,
            timeout=LLM_REQ_TIMEOUT,
        )
    from langchain_openai import ChatOpenAI
    logger.info("使用 OpenAI 兼容 API，model=%s, base_url=%s", settings.LLM_MODEL, base_url)
    return ChatOpenAI(
        base_url=base_url,
        api_key=api_key or "EMPTY",
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        timeout=LLM_REQ_TIMEOUT,
    )


# 面向楼下的备用工厂，便于替换 provider
def get_llm():
    return _build_llm()


RESUME_EXTRACT_SYSTEM = """你是简历解析专员。从简历文本提取所有信息，**只返回紧凑JSON（不要任何解释、不要markdown、不要多余换行缩进）**。

JSON结构（严格遵守，字段名不要改）：
{"name":"姓名","phone":"电话","email":"邮箱","location":"地址","job_title":"求职意向","github":"GitHub/个人主页链接（没有填空串）","sections":[
 {"t":"模块类型枚举","title":"模块标题","items":[{"h":"标题","s":"副标题","d":"时间","c":"详细描述，保留所有要点数字，不要省略"}]}
]}

模块类型t只能取：education|skills|experience|projects|awards|certificates|summary|interests|other

规则：
1. 不要输出basic类型模块，姓名电话邮箱已在顶层字段
2. 专业技能模块t=skills，items里放技能条目：可按技能类别分条（h填技能类别如"编程语言"，c填具体技能如"熟练掌握Java、Python，了解C++"），如果简历是简单技能列表，则h为空，c里用顿号分隔列出所有技能，保留所有技能不要省略
3. 自我评价模块t=summary，items里只放一个条目，c写完整自我评价
4. 每条经历/项目/教育都单独一个item，c字段务必保留原文所有要点、量化数字、技术栈，不要省略
5. 没有的字段填空字符串，没有的模块不要输出
6. **必须输出紧凑JSON：无多余空格换行，节省token**
7. 所有内容使用中文
"""

RESUME_IMPROVE_SYSTEM = """你是资深简历优化顾问。对用户提供的简历做专业改良，**只返回紧凑JSON**（不要任何解释、markdown、多余换行缩进）。

改良要点：
- 语言精炼、用词专业，突出可量化成果与亮点
- 完整保留原有模块结构（教育背景、技能、实习/项目经历、自我评价等），只优化内容不丢失内容
- 若附带岗位要求，务必结合岗位定向优化，突出与岗位匹配的技能与经历
- 不得编造原文不存在的经历、数字或技能；只做改写、重组与表述优化
- 所有内容使用中文

JSON结构（字段名不要改）：
{"name":"姓名","phone":"电话","email":"邮箱","location":"地址","job_title":"求职意向","github":"GitHub/个人主页链接（没有填空串）","sections":[
 {"t":"education|skills|experience|projects|awards|certificates|summary|interests|other","title":"模块标题","items":[{"h":"标题","s":"副标题","d":"时间","c":"详细描述，保留所有要点数字"}]}
]}

规则：
1. 不要输出basic模块，姓名电话邮箱已在顶层
2. 专业技能模块t=skills，items里放技能条目：可按类别分条描述，也可用一段完整文本描述技能水平，确保所有技能都完整列出不遗漏
3. summary模块items只放一个条目
4. c字段保留所有要点、量化数字、技术栈
5. 没有的字段填空字符串；必须输出完整改良后的简历，不要遗漏模块
"""


def _extract_text_chain(system_prompt: str):
    prompt = ChatPromptTemplate.from_messages(
        # system 用纯文本消息，避免 {JSON} 花括号被当作 f-string 模板解析而报错
        [SystemMessage(content=system_prompt), ("human", "{text}")]
    )
    return prompt | _build_llm() | StrOutputParser()


def _robust_json_parse(text: str) -> dict:
    """稳健解析 LLM 输出的 JSON：容忍 markdown 代码块、前后噪声、截断不完整。"""
    if not text:
        return {}
    s = text.strip()
    # 去掉 ```json ... ``` 代码块标记
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s)
    # 从第一个 { 开始截取
    start = s.find("{")
    if start == -1:
        return {}
    s = s[start:]
    # 尝试1：直接解析
    try:
        return json.loads(s)
    except Exception:
        pass
    # 尝试2：截取到最后一个 } 再解析（有结尾括号的情况）
    end = s.rfind("}")
    if end > 0:
        try:
            return json.loads(s[: end + 1])
        except Exception:
            pass
    # 尝试3：清理控制字符再解析
    try:
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
        return json.loads(cleaned)
    except Exception:
        pass
    # 尝试4：截断修复（最兜底）——补齐缺失的闭合括号
    try:
        return _repair_truncated_json(s)
    except Exception as e:
        logger.debug("JSON截断修复失败: %s", e)
        return {}


def _repair_truncated_json(s: str) -> dict:
    """修复因 max_tokens 截断而不完整的 JSON：补齐缺失的闭合括号与引号。"""
    stack: list[str] = []
    in_str = False
    escape = False
    out: list[str] = []
    for ch in s:
        out.append(ch)
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch == "}":
            if stack and stack[-1] == "}":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "]":
                stack.pop()
    # 字符串未闭合则补一个引号
    if in_str:
        out.append('"')
    # 补齐剩余闭合括号
    out.extend(reversed(stack))
    return json.loads("".join(out))


def extract_resume(text: str) -> dict:
    """LLM 结构化提取简历：返回含 name/phone/email/location/job_title/sections 的 dict。"""
    chain = _extract_text_chain(RESUME_EXTRACT_SYSTEM)
    try:
        logger.info("调用 LLM 提取简历，文本长度: %d", len(text))
        raw = chain.invoke({"text": text[:20000]}) or ""
        logger.info("LLM 返回长度: %d", len(raw))
        result = _robust_json_parse(raw)
        if not result:
            logger.warning("LLM JSON 解析失败，返回原文起始: %s", raw[:300])
            return {}
        normalized = _normalize_resume_payload(result)
        logger.info(
            "规范化后: sections=%d项",
            len(normalized.get("sections", []))
        )
        return normalized
    except Exception as e:
        logger.exception("简历 LLM 结构化提取失败: %s", str(e))
        return {}


def improve_resume(resume_text: str, job_requirement: str | None = None) -> dict:
    """AI 改良简历：返回结构化数据 dict（含 name/phone/.../sections），失败返回空 dict。"""
    chain = _extract_text_chain(RESUME_IMPROVE_SYSTEM)
    text = resume_text
    if job_requirement and job_requirement.strip():
        text = f"【岗位要求】\n{job_requirement.strip()}\n\n【简历原文】\n{resume_text}"
    try:
        raw = chain.invoke({"text": text[:20000]}) or ""
        logger.info("AI 改良 LLM 返回长度: %d", len(raw))
        parsed = _robust_json_parse(raw)
        if not parsed:
            logger.warning("AI 改良 JSON 解析失败，原文起始: %s", raw[:300])
            return {}
        return _normalize_resume_payload(parsed)
    except Exception:
        logger.exception("简历 LLM 改良失败")
        return {}


def _normalize_resume_payload(data: dict) -> dict:
    sections = _normalize_sections(data.get("sections"))
    # 兼容旧字段（从新sections回退构建，保证向量文本和旧字段正常）
    education, skills, experience, summary = [], [], [], ""
    for sec in sections:
        if sec["type"] == "education":
            for it in sec["items"]:
                education.append({
                    "school": it["heading"],
                    "major": it["subheading"],
                    "degree": "",
                    "start_date": "",
                    "end_date": it["date"],
                    "description": it["description"]
                })
        elif sec["type"] == "skills":
            for it in sec["items"]:
                if it["description"]:
                    for sk in re.split(r"[、,，\s]+", it["description"]):
                        sk = sk.strip()
                        if sk:
                            skills.append(sk)
                elif it["heading"]:
                    skills.append(it["heading"])
        elif sec["type"] in ("experience", "projects"):
            for it in sec["items"]:
                experience.append({
                    "type": "项目" if sec["type"] == "projects" else "实习",
                    "company": it["heading"],
                    "title": it["subheading"],
                    "start_date": "",
                    "end_date": it["date"],
                    "content": it["description"]
                })
        elif sec["type"] == "summary" and sec["items"]:
            summary = sec["items"][0]["description"]
    # 如果顶层直接有旧字段，优先用（兼容旧输出）
    if isinstance(data.get("education"), list) and data["education"]:
        education = [_normalize_edu(e) for e in data["education"] if isinstance(e, dict)]
    if isinstance(data.get("skills"), list) and data["skills"]:
        skills = [str(s).strip() for s in data["skills"] if str(s).strip()]
    if isinstance(data.get("experience"), list) and data["experience"]:
        experience = [_normalize_exp(e) for e in data["experience"] if isinstance(e, dict)]
    if data.get("summary"):
        summary = str(data.get("summary") or "").strip()
    return {
        "name": str(data.get("name", "") or "").strip(),
        "phone": str(data.get("phone", "") or "").strip(),
        "email": str(data.get("email", "") or "").strip(),
        "location": str(data.get("location", "") or "").strip(),
        "job_title": str(data.get("job_title", "") or "").strip(),
        "github": str(data.get("github", "") or "").strip(),
        "sections": sections,
        "education": education,
        "skills": skills,
        "experience": experience,
        "summary": summary,
    }


_ALLOWED_SECTION_TYPES = {
    "basic", "education", "skills", "experience",
    "projects", "awards", "certificates", "summary",
    "interests", "other",
}


def _normalize_sections(raw) -> list:
    """规范化动态模块结构：支持长短字段名、skills数组、条目映射。"""
    if not isinstance(raw, list):
        return []
    sections: list = []
    for sec in raw:
        if not isinstance(sec, dict):
            continue
        # 支持 type/t 两种字段名
        stype = str(sec.get("type") or sec.get("t") or "other").strip().lower()
        if stype not in _ALLOWED_SECTION_TYPES:
            stype = "other"
        title = str(sec.get("title", "") or "").strip() or stype
        items = []
        # 处理技能数组（旧格式短格式）：转换为文本条目
        if stype == "skills" and isinstance(sec.get("skills"), list):
            skill_texts = []
            for skill in sec["skills"]:
                s = str(skill).strip()
                if s:
                    skill_texts.append(s)
            if skill_texts:
                items.append({"heading": "", "subheading": "", "date": "", "description": "、".join(skill_texts)})
        else:
            raw_items = sec.get("items")
            if isinstance(raw_items, list):
                for it in raw_items:
                    if not isinstance(it, dict):
                        continue
                    # 支持长字段名和短字段名(h/s/d/c)
                    items.append({
                        "heading": str(it.get("heading") or it.get("h") or "").strip(),
                        "subheading": str(it.get("subheading") or it.get("s") or "").strip(),
                        "date": str(it.get("date") or it.get("d") or "").strip(),
                        "description": str(it.get("description") or it.get("c") or "").strip(),
                    })
        # 如果skills模块没有items但有顶层旧字段skills数组，兜底处理
        if stype == "skills" and not items and isinstance(sec.get("skills"), list):
            skill_texts = [str(s).strip() for s in sec["skills"] if str(s).strip()]
            if skill_texts:
                items.append({"heading": "", "subheading": "", "date": "", "description": "、".join(skill_texts)})
        sections.append({"type": stype, "title": title, "items": items})
    return sections


def _normalize_edu(e: dict) -> dict:
    return {
        "school": str(e.get("school", "") or "").strip(),
        "major": str(e.get("major", "") or "").strip(),
        "degree": str(e.get("degree", "") or "").strip(),
        "start_date": str(e.get("start_date", "") or "").strip(),
        "end_date": str(e.get("end_date", "") or "").strip(),
        "description": str(e.get("description", "") or "").strip(),
    }


def _normalize_exp(e: dict) -> dict:
    return {
        "type": str(e.get("type", "实习") or "实习").strip(),
        "company": str(e.get("company", "") or "").strip(),
        "title": str(e.get("title", "") or "").strip(),
        "start_date": str(e.get("start_date", "") or "").strip(),
        "end_date": str(e.get("end_date", "") or "").strip(),
        "content": str(e.get("content", "") or "").strip(),
    }