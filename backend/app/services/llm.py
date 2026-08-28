"""LLM 封装层：支持 OpenAI 兼容 API 与 Ollama(ChatOllama)。

- 提取模式：ChatPromptTemplate | LLM | StrOutputParser，返回结构化简历字段。
- 兼容：base_url 指向 Ollama 的 /v1 时，langchain_openai 也可以直连；
  也可直接使用 langchain_ollama.ChatOllama（本地）。由配置决定。
"""
import json
import logging
import re

from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.config import settings

logger = logging.getLogger(__name__)

# 云 API 单次请求超时（秒）：过长会拖慢整体流程，缩短快速失败
LLM_REQ_TIMEOUT = 120


def _msg_text(message) -> str:
    """兼容 langchain-core 新旧版本 .text 属性/方法，text 缺失时回退 content。"""
    t = getattr(message, "text", None)
    if t is None:
        return str(getattr(message, "content", ""))
    if callable(t):
        return str(t())
    return str(t)


def _build_llm(model: str | None = None):
    """构建并复用同一个 LLM 客户端实例。

    进程内只创建一次，携带连接池与 keep-alive，避免每次调用反复握手建连，
    从而显著降低多次 AI 请求的往返延迟，且不影响传给 LLM 的任何内容。

    Args:
        model: 覆盖默认配置的模型名（如 "glm-4v-flash"），不传则使用 settings.LLM_MODEL
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
    actual_model = model or settings.LLM_MODEL
    if uses_local_ollama:
        # 本地 Ollama：走 ChatOllama
        from langchain_ollama import ChatOllama
        host = settings.OLLAMA_HOST.rstrip("/")
        logger.info("使用 ChatOllama，model=%s, host=%s", actual_model, host)
        return ChatOllama(
            model=actual_model,
            base_url=host,
            temperature=settings.LLM_TEMPERATURE,
            num_predict=settings.LLM_MAX_TOKENS,
            timeout=LLM_REQ_TIMEOUT,
        )
    from langchain_openai import ChatOpenAI
    logger.info("使用 OpenAI 兼容 API，model=%s, base_url=%s", actual_model, base_url)
    return ChatOpenAI(
        base_url=base_url,
        api_key=api_key or "EMPTY",
        model=actual_model,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        timeout=LLM_REQ_TIMEOUT,
    )


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

【items字段严格格式（按模块类型填写）】
每个item = {"h":"标题","s":"副标题","d":"时间","c":"详细描述"}：
- 实习/工作(experience)：h=公司名（简短≤15字），s=职位，d=时间段（YYYY/MM-YYYY/MM），c=工作内容（不要把公司/职位/时间写进c）
- 项目(projects)：h=项目名（≤15字），s=角色（可空），d=时间段，c=项目描述；**http/https链接归顶层github字段，禁止出现在c里**
- 教育(education)：h=学校名，s=专业·学历，d=时间段，c=亮点/课程（可空）
- 获奖/证书：h=奖项名，s=颁发机构（可空），d=时间，c=补充（可空）
- 技能(skills)：h=类别（可空），s=""，d=""，c=技能文本
- 自我评价(summary)：h="",s="",d="",c=自我评价全文
【严格禁止】把时间放s/h、在c里放URL链接、h过长、c重复h/s/d的内容
"""

RESUME_ADVICE_SYSTEM = """你是资深 HR 与技术面试官，任务是**诊断简历并给出优化建议**——只建议，不改写整份简历。**只返回紧凑JSON（不要任何解释、markdown、多余换行缩进）**。

【评估方法论】
- 招聘者平均只花 7-11 秒 F 型扫描简历：姓名、当前/上一段头衔、公司、时间、教育最抓注意力；量化成果能显著提高简历回复率
- Bullet 质量用 XYZ 公式检验：「通过做 Z，实现了以 Y 度量的 X」；再用 So What 三连问检验（所以呢？→ 为什么重要？→ 这改变了什么？）
- 量化不限于硬数字：范围、频率、规模、代理指标、对比表述均可
- 动词等级传递资历信号（开发/搭建=执行层，主导/推动/负责=OWNER 层）；同一动词全文不超过两次
- 警惕 AI 生成味：过度润色、套话堆砌、模板化表述会引起招聘者怀疑
- 应届生/校招校准：1 页为宜、教育背景靠前；缺硬数字处可用可核验的代理表述（覆盖 XX 人 / XX 门课程前 10%）

JSON结构（字段名不要改）：
{"overall_score": 0到100整数, "summary": "一句话总评", "dimension_ratings": [{"name": "维度名", "rating": "强|中|弱", "evidence": "一句话证据"}], "items": [{"module": "模块名", "priority": "high|medium|low", "issue": "问题描述", "advice": "具体怎么改"}]}

dimension_ratings 固定 5 个维度：ATS兼容、招聘者扫描、Bullet质量、资历信号、关键词覆盖

要求：
1. items 输出 4-8 条建议，按 priority 从高到低排序；priority 含义：high=明显硬伤/严重失分，medium=值得改进，low=锦上添花
2. issue 必须引用简历原文的具体内容，并点明违反了哪条检验（如 XYZ 公式、So What、7秒扫描、动词重复），禁止"不够量化""缺乏亮点"这类不落地空话
3. advice 给出**可直接照抄的修改后表述示例**（必要时含简短改法说明），用户拿着就能替换进自己的简历
4. 若输入含【岗位要求】，优先围绕岗位匹配度（关键词覆盖）给建议；未提供则按简历 job_title 推断的通用技术岗位画像
5. 所有内容使用中文
"""


def _extract_text_chain(system_prompt: str):
    prompt = ChatPromptTemplate.from_messages(
        # system 用纯文本消息，避免 {JSON} 花括号被当作 f-string 模板解析而报错
        [SystemMessage(content=system_prompt), ("human", "{text}")]
    )
    llm = _build_llm()
    # JSON 模式在 API 层强制合法 JSON 输出，杜绝结构错乱；Ollama 原生协议不支持该参数，仅对 OpenAI 兼容客户端启用
    from langchain_openai import ChatOpenAI
    if isinstance(llm, ChatOpenAI):
        llm = llm.bind(response_format={"type": "json_object"})
    return prompt | llm | StrOutputParser()


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
    # 尝试3：清理控制字符（含字符串值内意外的字面换行/回车等，这是 LLM 非法 JSON 的最常见来源）
    # 合法 JSON 只允许这些字符以 \n \t 等转义序列出现；字面控制符会直接导致 json.loads 失败，
    # 全部替换为空格既修复这类错误，又不影响合法 JSON（换行/tab 作为结构空白本就等价于空格）。
    try:
        cleaned = re.sub(r"[\x00-\x1f]", " ", s)
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


def advise_resume(resume_text: str, job_requirement: str | None = None) -> dict:
    """AI 诊断简历：返回 {"overall_score", "summary", "items":[...]}，失败返回空 dict。"""
    chain = _extract_text_chain(RESUME_ADVICE_SYSTEM)
    text = resume_text
    if job_requirement and job_requirement.strip():
        text = f"【岗位要求】\n{job_requirement.strip()}\n\n【简历原文】\n{resume_text}"
    try:
        raw = chain.invoke({"text": text[:20000]}) or ""
        logger.info("AI 建议 LLM 返回长度: %d", len(raw))
        parsed = _robust_json_parse(raw)
        if not parsed or not parsed.get("items"):
            logger.warning("AI 建议 JSON 解析失败，原文起始: %s", raw[:300])
            return {}
        items = []
        for it in parsed["items"]:
            if not isinstance(it, dict):
                continue
            priority = str(it.get("priority", "medium") or "medium").strip().lower()
            if priority not in ("high", "medium", "low"):
                priority = "medium"
            items.append({
                "module": str(it.get("module", "") or "").strip() or "综合",
                "priority": priority,
                "issue": str(it.get("issue", "") or "").strip(),
                "advice": str(it.get("advice", "") or "").strip(),
            })
        if not items:
            return {}
        ratings = []
        for d in parsed.get("dimension_ratings") or []:
            if not isinstance(d, dict):
                continue
            rating = str(d.get("rating", "") or "").strip()
            if rating not in ("强", "中", "弱"):
                rating = "中"
            ratings.append({
                "name": str(d.get("name", "") or "").strip(),
                "rating": rating,
                "evidence": str(d.get("evidence", "") or "").strip(),
            })
        return {
            "overall_score": int(parsed.get("overall_score") or 0),
            "summary": str(parsed.get("summary", "") or "").strip(),
            "dimension_ratings": ratings,
            "items": items,
        }
    except Exception:
        logger.exception("AI 简历建议生成失败")
        return {}


def _normalize_resume_payload(data: dict) -> dict:
    sections = _normalize_sections(data.get("sections"))
    top_github = str(data.get("github", "") or "").strip()
    # 后处理：纠正常见字段错位（链接混入描述、时间错位、重复前缀等）
    sections, top_github = _post_clean_sections(sections, top_github)
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
    return {
        "name": str(data.get("name", "") or "").strip(),
        "phone": str(data.get("phone", "") or "").strip(),
        "email": str(data.get("email", "") or "").strip(),
        "location": str(data.get("location", "") or "").strip(),
        "job_title": str(data.get("job_title", "") or "").strip(),
        "github": top_github,
        "sections": sections,
        "education": education,
        "skills": skills,
        "experience": experience,
        "summary": summary,
        "changes": _normalize_changes(data.get("changes")),
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


# 时间格式正则：匹配 2025/07、2025-07、2025.07、2025年07月，以及范围 2025/07-2025/08、2025/07 - 至今
_DATE_RE = re.compile(
    r"^\s*(\d{4}\s*[/.\-年]\s*\d{1,2}\s*月?)"
    r"(?:\s*[-–~至到]\s*(\d{4}\s*[/.\-年]\s*\d{1,2}\s*月?|至今|现在|present|now))?\s*[：:\-\s]*"
)
# URL 正则
_URL_RE = re.compile(r"https?://[^\s，。；,;）)】\]]+")


def _post_clean_sections(sections: list, top_github: str) -> tuple[list, str]:
    """对规范化后的 sections 做后处理纠偏：
    1. 从 description 开头/正文提取 URL，补到顶层 github（若为空）
    2. 时间错位纠正：date 为空时，从 subheading 或 description 开头提取时间
    3. 清理 description 开头重复的公司/项目名、残留时间前缀
    """
    for sec in sections:
        stype = sec.get("type", "")
        for item in sec.get("items", []):
            h = (item.get("heading") or "").strip()
            s = (item.get("subheading") or "").strip()
            d = (item.get("date") or "").strip()
            c = (item.get("description") or "").strip()

            # --- 1) 从 c 中提取 URL ---
            urls = _URL_RE.findall(c)
            if urls:
                # 优先取 github.com 链接补顶层 github
                if not top_github:
                    gh = next((u for u in urls if "github.com" in u.lower()), urls[0])
                    top_github = gh.rstrip('，。；,;。')
                # 从 c 中移除所有 URL（连同行首残留标点空白）
                for u in urls:
                    c = c.replace(u, "")
                c = re.sub(r"^\s*[：:·\-–—\s]+", "", c).strip()

            # --- 2) 时间字段错位纠正 ---
            if not d:
                # 优先从 s 里提取时间（LLM 常把时间塞到 s）
                m = _DATE_RE.match(s)
                if m:
                    end = m.group(2) or ""
                    d = (m.group(1) + ("-" + end if end else "")).strip()
                    s = s[m.end():].strip(" ，,：:·-–—")
                else:
                    # 再尝试从 c 开头提取时间
                    m = _DATE_RE.match(c)
                    if m:
                        end = m.group(2) or ""
                        d = (m.group(1) + ("-" + end if end else "")).strip()
                        c = c[m.end():].strip()

            # --- 3) 清理 c 开头重复的标题/时间 ---
            if h:
                # 如果 c 以 h 开头（LLM 常重复写一遍公司/项目名），去除
                if c.startswith(h):
                    c = c[len(h):].lstrip(" ，,：:·-–—\n")
            if d and not h:
                pass
            # 去除 c 开头的多余标点/空白
            c = re.sub(r"^[\s：:·\-–—、，,]+", "", c).strip()

            # 技能模块：s/d 必须为空
            if stype == "skills":
                s = ""
                d = ""
            # 自我评价模块：h/s/d 必须为空
            if stype == "summary":
                h = ""
                s = ""
                d = ""

            item["heading"] = h
            item["subheading"] = s
            item["date"] = d
            item["description"] = c
    return sections, top_github


def _normalize_changes(raw) -> list:
    """规范化 LLM 输出的 changes 变更说明数组。"""
    if not isinstance(raw, list):
        return []
    changes = []
    for ch in raw:
        if not isinstance(ch, dict):
            continue
        changes.append({
            "module": str(ch.get("module", "") or ch.get("title", "") or "").strip(),
            "action": str(ch.get("action", "保留") or "保留").strip(),
            "summary": str(ch.get("summary", "") or ch.get("desc", "") or "").strip(),
        })
    return changes


def _bind_tools(llm, tools):
    """把工具绑定到 LLM 实例；模型/后端不支持工具调用时安全降级。

    返回 (llm_or_bound, ok)：
    - ok=True：调用方应使用 llm_or_bound（已绑定工具）驱动 ReAct 循环；
    - ok=False：当前配置不支持工具调用（如 Ollama 原生协议），
      调用方应走纯文本降级路径（保持与现有行为等价）。
    """
    if not tools:
        return llm, True
    try:
        from langchain_core.tools import BaseTool

        for t in tools:
            if not isinstance(t, BaseTool):
                logger.warning("存在非法工具对象 %r，降级为纯文本模式", type(t))
                return llm, False
        return llm.bind_tools(tools), True
    except Exception as e:
        logger.warning("工具绑定失败，降级为纯文本模式: %s", e)
        return llm, False