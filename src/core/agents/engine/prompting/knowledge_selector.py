"""
Knowledge selector for dynamic prompt injection.

Selects relevant knowledge skills based on current goal and tool usage.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set

from ...state import AgentLoopState
from ...capabilities.skills import SkillRegistry


_DOMAIN_KEYWORDS = {
    "database": ["db", "sql", "mysql", "database", "query", "表", "数据库", "查询"],
    "http": ["http", "api", "url", "webhook", "request", "网页", "接口"],
    "task-management": [
        "task",
        "schedule",
        "scheduler",
        "trace_id",
        "cancel",
        "任务",
        "调度",
        "并发",
    ],
    "observability": [
        "log",
        "alert",
        "trace",
        "monitor",
        "observability",
        "日志",
        "告警",
        "监控",
    ],
}


@dataclass
class KnowledgeSelector:
    """Select relevant knowledge text for the current agent state.

    domain_keywords 可通过构造参数覆盖，也支持从 skill.tags 自动汇总：
      1. 显式传入 dict → 完全替换内置默认值
      2. 调用 auto_collect_domains(registry) 从已注册 skill 的 domain/tags 汇总
    """

    registry: SkillRegistry
    max_knowledge_tokens: int = 4000
    chars_per_token: float = 4.0
    domain_keywords: Dict[str, List[str]] = field(default_factory=lambda: dict(_DOMAIN_KEYWORDS))

    @staticmethod
    def auto_collect_domains(registry: SkillRegistry) -> Dict[str, List[str]]:
        """从 registry 中已注册 skill 汇总 domain 关键词映射"""
        collected: Dict[str, List[str]] = {}
        for skill in registry.filter(lambda _: True):
            domain = skill.domain or "general"
            if domain not in collected:
                collected[domain] = []
            keywords = list(skill.tags or [])
            keywords.append(skill.name)
            keywords.extend(skill.description.split())
            collected[domain].extend(keywords)
        # 去重并合并内置默认值
        merged = dict(_DOMAIN_KEYWORDS)
        for domain, keywords in collected.items():
            existing = set(merged.get(domain, []))
            existing.update(k.lower() for k in keywords if len(k) > 2)
            merged[domain] = list(existing)
        return merged

    def select(self, state: AgentLoopState) -> str:
        domains = self._infer_domains(state)
        if not domains:
            return ""

        selected = []
        seen = set()
        for domain in domains:
            for skill in self.registry.list_knowledge(domain=domain):
                if skill.name not in seen:
                    selected.append(skill)
                    seen.add(skill.name)

        if not selected:
            return ""

        parts: List[str] = []
        max_chars = int(self.max_knowledge_tokens * self.chars_per_token)
        used_chars = 0

        for skill in selected:
            text = skill.to_prompt_text().strip()
            if not text:
                continue
            chunk = f"## Knowledge: {skill.name}\n{text}"
            chunk_len = len(chunk)
            if parts and used_chars + chunk_len > max_chars:
                break
            parts.append(chunk)
            used_chars += chunk_len + 2

        return "\n\n".join(parts)

    def _infer_domains(self, state: AgentLoopState) -> List[str]:
        domains: List[str] = []
        seen: Set[str] = set()

        def add(domain: str) -> None:
            if domain and domain not in seen:
                domains.append(domain)
                seen.add(domain)

        goal_text = (state.goal or "").lower()
        for domain, keywords in self.domain_keywords.items():
            if any(keyword.lower() in goal_text for keyword in keywords):
                add(domain)

        for record in state.tool_call_history:
            tool_name = record.tool_name
            skill = self.registry.get(tool_name)
            if skill and skill.domain and skill.domain != "general":
                add(skill.domain)
            for domain, keywords in self.domain_keywords.items():
                if any(keyword.lower() in tool_name.lower() for keyword in keywords):
                    add(domain)

        return domains


__all__ = ["KnowledgeSelector"]
