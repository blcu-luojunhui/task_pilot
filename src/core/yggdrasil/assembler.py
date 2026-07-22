"""
Yggdrasil 认知架构 —— 上下文组装器

ContextAssembler 将 SubtreeResult 转换为 LLM 可读的 prompt 文本，
替代当前 KnowledgeSelector 的散点检索输出。
"""

from typing import Any, Dict

from .models import NodeType, SubtreeResult, TreeNode


class ContextAssembler:
    """将子树检索结果组装为 LLM prompt 文本"""

    def assemble_prompt_injection(self, subtree: SubtreeResult) -> str:
        """
        生成格式化的上下文注入文本。

        输出格式示例：

        ## 相关能力 (Skills)
        - skill-database-query: 执行只读 SQL 查询，支持参数化查询...

        ## 相关知识 (Knowledge)
        - database-query-patterns: MySQL 查询最佳实践：使用索引...

        ## 历史经验 (Memories)
        - 上次执行 database-query 时，发现 LIKE 查询在高并发下...
        """
        if not subtree.nodes:
            return ""

        skills = [n for n in subtree.nodes if n.node_type == NodeType.SKILL]
        knowledge = [n for n in subtree.nodes if n.node_type == NodeType.KNOWLEDGE]
        memories = [n for n in subtree.nodes if n.node_type == NodeType.MEMORY]

        sections = []

        if skills:
            sections.append("## 相关能力 (Skills)\n" + self._format_node_list(skills))

        if knowledge:
            sections.append("## 相关知识 (Knowledge)\n" + self._format_node_list(knowledge))

        if memories:
            sections.append("## 历史经验 (Memories)\n" + self._format_node_list(memories))

        return "\n\n".join(sections) if sections else ""

    def assemble_structured_context(self, subtree: SubtreeResult) -> Dict[str, Any]:
        """返回结构化上下文，供 PromptAssembler 精确使用"""
        return {
            "skills": [
                {"id": n.id, "title": n.title, "content": n.content, "summary": n.summary}
                for n in subtree.nodes if n.node_type == NodeType.SKILL
            ],
            "knowledge": [
                {"id": n.id, "title": n.title, "content": n.content, "summary": n.summary}
                for n in subtree.nodes if n.node_type == NodeType.KNOWLEDGE
            ],
            "memories": [
                {"id": n.id, "title": n.title, "content": n.content}
                for n in subtree.nodes if n.node_type == NodeType.MEMORY
            ],
            "total_tokens_estimate": subtree.total_tokens_estimate,
        }

    @staticmethod
    def _format_node_list(nodes: list[TreeNode]) -> str:
        """将节点列表格式化为 bullet list"""
        lines = []
        for node in nodes:
            text = node.summary or node.content or ""
            # 截断过长的内容，保留摘要
            if len(text) > 200:
                text = text[:200] + "..."
            lines.append(f"- **{node.title}**: {text}")
        return "\n".join(lines)


__all__ = ["ContextAssembler"]