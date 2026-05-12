"""
多 Agent 协调器

负责管理多个 Agent 并协调它们完成复杂任务
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

from .bus import MessageBus
from .protocol import Message, MessageType
from ..engine.agent import Agent

logger = logging.getLogger(__name__)

# Agent 心跳超时（秒）
_HEARTBEAT_TIMEOUT = 60.0


@dataclass
class TaskAssignment:
    """任务分配"""

    task_id: str
    agent_id: str
    task: str
    status: str = "pending"  # pending, running, completed, failed
    result: Optional[Any] = None
    error: Optional[str] = None


class MultiAgentCoordinator:
    """多 Agent 协调器"""

    def __init__(self, bus: Optional[MessageBus] = None, planner_agent_id: Optional[str] = None):
        """
        初始化协调器

        Args:
            bus: 消息总线（可选，默认创建新的）
            planner_agent_id: 指定负责任务分解的 Agent ID（None 则自动选择）
        """
        self.bus = bus or MessageBus()
        self.agents: Dict[str, Agent] = {}
        self.assignments: Dict[str, TaskAssignment] = {}
        self.planner_agent_id = planner_agent_id

        # Agent 健康追踪
        self._last_heartbeat: Dict[str, float] = {}
        self._agent_healthy: Dict[str, bool] = {}

        # 结果回调
        self._pending_results: Dict[str, asyncio.Event] = {}

        # 订阅消息
        self.bus.subscribe(MessageType.RESULT, self._handle_result)
        self.bus.subscribe(MessageType.HEARTBEAT, self._handle_heartbeat)

    def register_agent(self, agent_id: str, agent: Agent):
        """
        注册 Agent

        Args:
            agent_id: Agent ID
            agent: Agent 实例
        """
        self.agents[agent_id] = agent
        self.bus.register_agent(agent_id)
        logger.info(f"Agent {agent_id} registered with coordinator")

    def unregister_agent(self, agent_id: str):
        """
        注销 Agent

        Args:
            agent_id: Agent ID
        """
        if agent_id in self.agents:
            del self.agents[agent_id]
        self.bus.unregister_agent(agent_id)
        logger.info(f"Agent {agent_id} unregistered from coordinator")

    async def coordinate(
        self,
        task: str,
        strategy: str = "parallel",  # parallel, sequential, dynamic
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        协调多个 Agent 完成任务

        Args:
            task: 任务描述
            strategy: 执行策略（parallel/sequential/dynamic）
            context: 任务上下文

        Returns:
            任务结果
        """
        logger.info(f"Coordinating task with strategy: {strategy}")

        # 1. 任务分解
        sub_tasks = await self._decompose_task(task, context)
        logger.info(f"Task decomposed into {len(sub_tasks)} sub-tasks")

        # 2. 任务分配
        assignments = self._assign_tasks(sub_tasks, strategy)

        # 3. 执行任务
        if strategy == "parallel":
            results = await self._execute_parallel(assignments)
        elif strategy == "sequential":
            results = await self._execute_sequential(assignments)
        else:
            results = await self._execute_dynamic(assignments)

        # 4. 聚合结果
        return self._aggregate_results(results)

    async def _decompose_task(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        任务分解

        Args:
            task: 任务描述
            context: 任务上下文

        Returns:
            子任务列表
        """
        if not self.agents:
            return [task]

        # 优先使用指定的 planner agent，否则按 capability tag 匹配，最后 fallback 到第一个
        planner_agent: Optional[Agent] = None
        if self.planner_agent_id and self.planner_agent_id in self.agents:
            planner_agent = self.agents[self.planner_agent_id]
        else:
            for agent_id, agent in self.agents.items():
                if hasattr(agent, '_registry'):
                    # 优先选择有 planning 能力的 agent
                    planner_agent = agent
                    break
        if planner_agent is None:
            planner_agent = list(self.agents.values())[0]

        prompt = f"""将以下任务分解为可并行执行的子任务。

任务：{task}

要求：
1. 每个子任务应该独立且可并行执行
2. 返回 JSON 格式的子任务列表
3. 格式：["子任务1", "子任务2", ...]

如果任务无法分解，返回包含原任务的列表。
"""

        try:
            result = await planner_agent.run(prompt)
            # 尝试解析 JSON
            sub_tasks = json.loads(result.final_answer)
            if isinstance(sub_tasks, list) and all(isinstance(t, str) for t in sub_tasks):
                return sub_tasks
        except Exception as e:
            logger.warning(f"Task decomposition failed: {e}")

        # 分解失败，返回原任务
        return [task]

    def _assign_tasks(self, tasks: List[str], strategy: str) -> List[TaskAssignment]:
        """
        任务分配

        Args:
            tasks: 任务列表
            strategy: 执行策略

        Returns:
            任务分配列表
        """
        assignments = []
        agent_ids = list(self.agents.keys())

        if not agent_ids:
            raise ValueError("No agents available for task assignment")

        for i, task in enumerate(tasks):
            # 简单的轮询分配
            agent_id = agent_ids[i % len(agent_ids)]

            assignment = TaskAssignment(
                task_id=f"task_{i}_{id(task)}", agent_id=agent_id, task=task
            )
            assignments.append(assignment)
            self.assignments[assignment.task_id] = assignment

        return assignments

    async def _execute_parallel(self, assignments: List[TaskAssignment]) -> List[TaskAssignment]:
        """
        并行执行任务

        Args:
            assignments: 任务分配列表

        Returns:
            完成的任务分配列表
        """
        tasks = []

        for assignment in assignments:
            agent = self.agents[assignment.agent_id]
            assignment.status = "running"

            # 创建异步任务
            task = asyncio.create_task(self._execute_assignment(agent, assignment))
            tasks.append(task)

        # 等待所有任务完成
        await asyncio.gather(*tasks, return_exceptions=True)

        return assignments

    async def _execute_sequential(self, assignments: List[TaskAssignment]) -> List[TaskAssignment]:
        """
        顺序执行任务

        Args:
            assignments: 任务分配列表

        Returns:
            完成的任务分配列表
        """
        for assignment in assignments:
            agent = self.agents[assignment.agent_id]
            assignment.status = "running"

            await self._execute_assignment(agent, assignment)

            # 如果失败，停止后续任务
            if assignment.status == "failed":
                logger.error(f"Task {assignment.task_id} failed, stopping sequential execution")
                break

        return assignments

    async def _execute_dynamic(self, assignments: List[TaskAssignment]) -> List[TaskAssignment]:
        """
        动态执行任务：逐个启动，完成一个后再启动下一个（流水线模式）

        Args:
            assignments: 任务分配列表

        Returns:
            完成的任务分配列表
        """
        completed: List[TaskAssignment] = []
        pending = list(assignments)

        while pending:
            # 取一个未启动的任务
            assignment = pending.pop(0)
            agent = self.agents[assignment.agent_id]
            assignment.status = "running"

            try:
                await self._execute_assignment(agent, assignment)
                completed.append(assignment)
            except Exception as e:
                logger.error(f"Dynamic task {assignment.task_id} failed: {e}")
                assignment.status = "failed"
                assignment.error = str(e)
                completed.append(assignment)
                # 动态模式：使用已完成结果影响后续任务（将结果注入为 context）
                if assignment.result:
                    for remaining in pending:
                        remaining.task = (
                            f"[Previous result: {assignment.result[:200]}] {remaining.task}"
                        )

        return completed

    async def _execute_assignment(self, agent: Agent, assignment: TaskAssignment):
        """
        执行单个任务分配

        Args:
            agent: Agent 实例
            assignment: 任务分配
        """
        try:
            logger.info(f"Executing task {assignment.task_id} on agent {assignment.agent_id}")

            result = await agent.run(assignment.task)

            assignment.result = result.final_answer
            assignment.status = "completed"

            logger.info(f"Task {assignment.task_id} completed")

        except Exception as e:
            logger.error(f"Task {assignment.task_id} failed: {e}")
            assignment.status = "failed"
            assignment.error = str(e)

    def _aggregate_results(self, assignments: List[TaskAssignment]) -> Dict[str, Any]:
        """
        聚合任务结果

        Args:
            assignments: 任务分配列表

        Returns:
            聚合后的结果
        """
        completed = [a for a in assignments if a.status == "completed"]
        failed = [a for a in assignments if a.status == "failed"]

        results = {
            "total_tasks": len(assignments),
            "completed": len(completed),
            "failed": len(failed),
            "success_rate": len(completed) / len(assignments) if assignments else 0,
            "results": [
                {
                    "task_id": a.task_id,
                    "agent_id": a.agent_id,
                    "task": a.task,
                    "result": a.result,
                    "status": a.status,
                    "error": a.error,
                }
                for a in assignments
            ],
        }

        return results

    async def _handle_result(self, message: Message):
        """处理异步结果回调"""
        logger.info(f"Received result from {message.sender}: {message.content}")

        # 根据 correlation_id 匹配 pending result
        correlation_id = message.correlation_id
        if correlation_id and correlation_id in self._pending_results:
            event = self._pending_results.pop(correlation_id)
            # 将结果写入对应的 assignment
            for assignment in self.assignments.values():
                if assignment.task_id == correlation_id:
                    assignment.result = message.content
                    assignment.status = "completed"
                    break
            event.set()
        else:
            logger.warning(f"No pending result found for correlation_id: {correlation_id}")

    async def _handle_heartbeat(self, message: Message):
        """处理心跳消息，追踪 Agent 健康状态"""
        agent_id = message.sender
        now = time.monotonic()
        self._last_heartbeat[agent_id] = now

        was_unhealthy = not self._agent_healthy.get(agent_id, True)
        self._agent_healthy[agent_id] = True

        if was_unhealthy:
            logger.info(f"Agent {agent_id} recovered (heartbeat received)")

    def check_agent_health(self) -> List[str]:
        """
        检查所有 Agent 健康状态

        Returns:
            超时的 Agent ID 列表
        """
        now = time.monotonic()
        timed_out = []
        for agent_id in self.agents:
            last_hb = self._last_heartbeat.get(agent_id, 0)
            if now - last_hb > _HEARTBEAT_TIMEOUT:
                self._agent_healthy[agent_id] = False
                timed_out.append(agent_id)
        return timed_out

    def get_status(self) -> Dict[str, Any]:
        """获取协调器状态"""
        return {
            "agents": list(self.agents.keys()),
            "agent_health": {
                aid: self._agent_healthy.get(aid, True) for aid in self.agents
            },
            "active_tasks": len([a for a in self.assignments.values() if a.status == "running"]),
            "completed_tasks": len(
                [a for a in self.assignments.values() if a.status == "completed"]
            ),
            "failed_tasks": len([a for a in self.assignments.values() if a.status == "failed"]),
            "bus_stats": self.bus.get_stats(),
        }


__all__ = ["MultiAgentCoordinator", "TaskAssignment"]
