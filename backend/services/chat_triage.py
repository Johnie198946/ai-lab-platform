"""Deterministic, server-owned request triage for Main chat.

The classifier intentionally has a conservative default: ambiguous requests are
ordinary Q&A.  Only explicit conversation markers become casual, and only
strong execution/deliverable signals become professional work.  Evidence needs
are orthogonal to task class so a URL does not automatically select an Agent.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


CASUAL = "CASUAL"
GENERAL_QA = "GENERAL_QA"
PROFESSIONAL_TASK = "PROFESSIONAL_TASK"
TRIAGE_VERSION = "2026-08-27.v1"

_URL_RE = re.compile(r"https?://[^\s<>\]\[)）]+", re.IGNORECASE)
_CASUAL_RE = re.compile(
    r"^(?:你?好|嗨|哈喽|hello|hi|hey|早上好|上午好|下午好|晚上好|"
    r"谢谢(?:你)?|多谢|谢了|好的|好呀|可以|行|收到|明白了|再见|晚安|"
    r"在吗|你在吗|最近怎么样|你好吗|哈哈+|嘿+)[!！。,.，?？~～\s]*$",
    re.IGNORECASE,
)
_SOCIAL_RE = re.compile(
    r"(?:陪我聊|聊聊天|讲个笑话|逗我开心|我(?:今天|最近)?(?:有点)?(?:难过|开心|累|烦)|"
    r"how are you|tell me a joke)",
    re.IGNORECASE,
)
_DIRECT_RESPONSE_RE = re.compile(
    r"^(?:(?:做个|进行|来个)?测试[:：，,\s]*)?"
    r"(?:你)?(?:只)?(?:回答|回复)(?:我)?\s*(?:ok|yes|no|收到|好的|[0-9])"
    r"[！!。,.，\s]*$|"
    r"^不要解释[，,\s]*(?:只)?输出\s*(?:[a-z0-9_-]{1,16}|[\u4e00-\u9fff]{1,8})"
    r"[！!。,.，\s]*$|"
    r"^按你(?:的)?建议(?:做|执行)[！!。,.，\s]*$",
    re.IGNORECASE,
)
_PROFESSIONAL_ACTION_RE = re.compile(
    r"(?:调研|研究|审计|诊断|排查|评估|分析|设计|制定|规划|开发|实现|搭建|"
    r"重构|优化|测试|验证|部署|迁移|复盘|建模|撰写|制作|生成|整理并保存|"
    r"写(?:一段|个|份)?(?:代码|脚本|程序)|"
    r"(?:做|创建|构建)(?:一个|一份)?(?:网站|应用|程序|原型|模型|报告|方案)|"
    r"research|audit|diagnose|assess|design|implement|develop|deploy|migrate|refactor)",
    re.IGNORECASE,
)
_HIGH_PROFESSIONAL_ACTION_RE = re.compile(
    r"(?:调研|研究|审计|诊断|排查|评估|设计|制定|规划|开发|实现|搭建|重构|"
    r"测试|验证|部署|迁移|建模|写(?:一段|个|份)?(?:代码|脚本|程序)|"
    r"(?:做|创建|构建)(?:一个|一份)?(?:网站|应用|程序|原型|模型|报告|方案)|"
    r"research|audit|diagnose|assess|design|implement|develop|deploy|migrate|refactor)",
    re.IGNORECASE,
)
_DELIVERABLE_RE = re.compile(
    r"(?:方案|报告|代码|脚本|架构|规划|路线图|设计稿|原型|营销计划|测试计划|"
    r"审计结论|模型|合同|PRD|SOP|清单|投标书|白皮书|可视化|仪表盘|"
    r"plan|report|roadmap|prototype|implementation|architecture|deliverable)",
    re.IGNORECASE,
)
_DEPTH_RE = re.compile(
    r"(?:深入|完整|系统性?|专业|严谨|详细|可执行|生产级|端到端|管理层|董事会|"
    r"comprehensive|professional|production[- ]ready|end[- ]to[- ]end)",
    re.IGNORECASE,
)
_CONSTRAINT_RE = re.compile(
    r"(?:必须|要求|约束|限制|预算|截止|风险|指标|合规|标准|性能|安全|法律|"
    r"财务|医疗|WCAG|SLA|KPI|ROI|包含.{0,30}(?:和|、|以及))",
    re.IGNORECASE,
)
_FRESH_RE = re.compile(
    r"(?:最新|今天|今日|今年|本年|本季度|本财年|当前|现在|近期|最近|实时|新闻|价格|行情|版本|发布于|"
    r"截至|latest|today|current|recent|news|price|version)",
    re.IGNORECASE,
)
_PUBLIC_RESEARCH_RE = re.compile(
    r"(?:全网|网上|公开资料|搜索|检索|查一下|搜一下|调研|研究|"
    r"web|internet|online|search|research)",
    re.IGNORECASE,
)
_INTERNAL_RE = re.compile(
    r"(?:内部|公司资料|企业知识|知识库|Wiki|笔记|我们(?:之前|聊过|的资料)|"
    r"internal|knowledge base|notes?)",
    re.IGNORECASE,
)
_BUSINESS_FACT_RE = re.compile(
    r"(?:财报|年报|半年报|季报|营收|营业收入|收入情况|净利润|毛利率|现金流|"
    r"出货量|市场份额|经营情况|业绩|产品线|客户情况|项目进展|竞争格局)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TriageDecision:
    route_class: str
    confidence: float
    reason_code: str
    evidence_requirements: tuple[str, ...] = ()

    def as_dict(
        self,
        *,
        agency_enabled: bool = False,
        skill_enabled: bool = False,
    ) -> dict[str, Any]:
        return {
            "version": TRIAGE_VERSION,
            "route_class": self.route_class,
            "confidence": round(self.confidence, 2),
            "reason_code": self.reason_code,
            "evidence_requirements": list(self.evidence_requirements),
            "agency_enabled": bool(
                agency_enabled and self.route_class == PROFESSIONAL_TASK
            ),
            "skill_enabled": bool(
                skill_enabled and self.route_class == PROFESSIONAL_TASK
            ),
        }


def _evidence_requirements(text: str) -> tuple[str, ...]:
    requirements: list[str] = []
    if _URL_RE.search(text):
        requirements.append("web_extract")
    # Business/company facts are local-knowledge-first by default. Freshness is
    # orthogonal: when both apply Hermes searches authorized knowledge first,
    # then supplements gaps from the public web.
    if _INTERNAL_RE.search(text) or _BUSINESS_FACT_RE.search(text):
        requirements.append("knowledge_search")
    if _FRESH_RE.search(text) or _PUBLIC_RESEARCH_RE.search(text):
        requirements.append("web_search")
    return tuple(dict.fromkeys(requirements))


def classify_request(
    question: str,
    *,
    explicit_agent: bool = False,
    explicit_skill: bool = False,
) -> TriageDecision:
    """Classify a single user turn without model latency or client authority."""
    text = " ".join(str(question or "").strip().split())
    evidence = _evidence_requirements(text)
    if explicit_agent or explicit_skill:
        return TriageDecision(
            PROFESSIONAL_TASK,
            0.99,
            "explicit_capability",
            evidence,
        )
    if not text:
        return TriageDecision(GENERAL_QA, 0.55, "empty_or_ambiguous", evidence)
    if _DIRECT_RESPONSE_RE.fullmatch(text):
        return TriageDecision(GENERAL_QA, 0.99, "direct_response", ())
    if not _URL_RE.search(text) and (
        _CASUAL_RE.fullmatch(text) or _SOCIAL_RE.search(text)
    ):
        return TriageDecision(CASUAL, 0.98, "conversation_marker", ())

    action = bool(_PROFESSIONAL_ACTION_RE.search(text))
    high_action = bool(_HIGH_PROFESSIONAL_ACTION_RE.search(text))
    deliverable = bool(_DELIVERABLE_RE.search(text))
    depth = bool(_DEPTH_RE.search(text))
    constraints = bool(_CONSTRAINT_RE.search(text))
    score = (3 if high_action else int(action) * 2)
    score += int(deliverable) * 2 + int(depth) + int(constraints)
    if len(text) >= 180:
        score += 1
    if action and evidence and any(
        item in evidence for item in ("web_extract", "web_search")
    ):
        score += 1

    if score >= 3:
        reason = "professional_action_and_deliverable"
        if action and "web_extract" in evidence:
            reason = "professional_url_research"
        elif action and "web_search" in evidence:
            reason = "professional_public_research"
        return TriageDecision(
            PROFESSIONAL_TASK,
            min(0.97, 0.72 + score * 0.04),
            reason,
            evidence,
        )

    reason = "evidence_qa" if evidence else "general_question"
    return TriageDecision(GENERAL_QA, 0.84 if evidence else 0.78, reason, evidence)
