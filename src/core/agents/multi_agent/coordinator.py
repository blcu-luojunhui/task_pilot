"""
多 Agent 协调器

负责管理多个 Agent 并协调它们完成复杂任务
"""

import asyncio
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

from .bus import MessageBus
from .protocol import Message, MessageType
from ..engine.agent import Agent

logger = logging.getLogger(__name__)


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

    def __init__(self, bus: Optional[MessageBus] = None):
        """
        初始化协调器

        Args:
            bus: 消息总线（可选，默认创建新的）
        """
        self.bus = bus or MessageBus()
        self.agents: Dict[str, Agent] = {}
        self.assignments: Dict[str, TaskAssignment] = {}

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

        # 使用第一个 Agent 进行任务分解
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
        动态执行任务（根据依赖关系）

        Args:
            assignments: 任务分配列表

        Returns:
            完成的任务分配列表
        """
        # TODO: 实现基于依赖关系的动态调度
        # 目前使用并行执行
        return await self._execute_parallel(assignments)

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
        """处理结果消息"""
        logger.info(f"Received result from {message.sender}")
        # TODO: 处理 Agent 返回的结果

    async def _handle_heartbeat(self, message: Message):
        """处理心跳消息"""
        logger.debug(f"Heartbeat from {message.sender}")

    def get_status(self) -> Dict[str, Any]:
        """获取协调器状态"""
        return {
            "agents": list(self.agents.keys()),
            "active_tasks": len([a for a in self.assignments.values() if a.status == "running"]),
            "completed_tasks": len(
                [a for a in self.assignments.values() if a.status == "completed"]
            ),
            "failed_tasks": len([a for a in self.assignments.values() if a.status == "failed"]),
            "bus_stats": self.bus.get_stats(),
        }


__all__ = ["MultiAgentCoordinator", "TaskAssignment"]
