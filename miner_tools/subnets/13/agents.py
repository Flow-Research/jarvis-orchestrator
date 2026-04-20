#!/usr/bin/env python3
"""
Agent Worker Layer for SN13 Task Execution

Workers that execute subtasks and return results.
"""

from __future__ import annotations
import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from decomposition import TaskDAG, SubTask, TaskStatus


@dataclass
class AgentResponse:
    """Response from agent execution."""

    task_id: str
    agent_id: str
    output: dict
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    @property
    def cost(self) -> float:
        return self.metadata.get("cost", 0.0)

    @property
    def latency_ms(self) -> float:
        return self.metadata.get("latency_ms", 0.0)


@dataclass
class VerificationResult:
    """Result from verification."""

    task_id: str
    is_valid: bool
    score: float
    reason: str = ""


class BaseAgent:
    """Base agent that executes tasks."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    async def execute(self, task: SubTask) -> AgentResponse:
        """Execute a subtask."""
        raise NotImplementedError

    async def verify(self, output: dict, expected: dict = None) -> VerificationResult:
        """Verify output."""
        return VerificationResult(task_id="", is_valid=True, score=1.0, reason="No verification")


class MockScraperAgent(BaseAgent):
    """Mock agent that simulates scraping data."""

    async def execute(self, task: SubTask) -> AgentResponse:
        """Simulate scraping work."""
        input_data = task.input_data
        chunk = input_data.get("chunk", 0)

        # Simulate some work
        await asyncio.sleep(0.1)

        # Return mock data
        output = {
            "data": [
                {
                    "content": f"Mock post {i} from chunk {chunk}",
                    "created_at": datetime.now().isoformat(),
                    "source": input_data.get("source", "X"),
                    "label": input_data.get("label", "test"),
                }
                for i in range(10)
            ]
        }

        return AgentResponse(
            task_id=task.subtask_id,
            agent_id=self.agent_id,
            output=output,
            metadata={"cost": 0.001, "latency_ms": 100.0},
        )


class AgentPool:
    """Pool of agents that execute tasks."""

    def __init__(self, agents: list[BaseAgent] = None):
        self.agents = agents or [MockScraperAgent(f"agent_{i}") for i in range(3)]
        self.current = 0

    def get_next(self) -> BaseAgent:
        """Round-robin get next agent."""
        agent = self.agents[self.current]
        self.current = (self.current + 1) % len(self.agents)
        return agent

    async def execute_task(self, task: SubTask) -> AgentResponse:
        """Execute task with available agent."""
        agent = self.get_next()
        return await agent.execute(task)

    async def execute_dag(self, dag: TaskDAG) -> dict:
        """Execute entire DAG and return aggregated result."""
        while True:
            ready = dag.get_ready_subtasks()
            if not ready:
                break

            # Execute each ready task
            for task in ready:
                task.status = TaskStatus.IN_PROGRESS
                response = await self.execute_task(task)

                # Mark completed
                task.status = TaskStatus.COMPLETED
                task.output = response.output
                task.assigned_agent = response.agent_id

            # Check if all done
            all_done = all(
                st.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
                for st in dag.subtasks.values()
            )
            if all_done:
                break

        return dag.get_result()


class VerificationEngine:
    """Verifies agent outputs."""

    def __init__(self, pool: AgentPool):
        self.pool = pool

    async def verify_output(self, output: dict, task: SubTask) -> VerificationResult:
        """Verify output quality."""
        # Basic checks
        if not output:
            return VerificationResult(
                task_id=task.subtask_id, is_valid=False, score=0.0, reason="Empty output"
            )

        data = output.get("data", [])
        if not data:
            return VerificationResult(
                task_id=task.subtask_id, is_valid=False, score=0.0, reason="No data"
            )

        # Check for required fields
        valid_count = sum(1 for d in data if d.get("content"))
        score = valid_count / len(data) if data else 0

        return VerificationResult(
            task_id=task.subtask_id,
            is_valid=score > 0.5,
            score=score,
            reason=f"{valid_count}/{len(data)} valid entries",
        )

    async def verify_with_redundancy(self, outputs: list[AgentResponse]) -> dict:
        """Verify using redundant execution (compare multiple agents)."""
        if len(outputs) < 2:
            return {"is_valid": True, "score": 1.0}

        # Compare outputs - simple majority vote
        # In production, you'd use IoU, semantic similarity, etc.
        results = [o.output for o in outputs]

        # If outputs are similar enough, mark valid
        return {"is_valid": True, "score": 1.0, "compared": len(outputs), "results": results}


# Example execution
if __name__ == "__main__":
    from decomposition import DecompositionEngine

    async def main():
        # Create decomposition
        engine = DecompositionEngine()
        dag = engine.decompose(
            "GetDataEntityBucket", {"expected_count": 300, "batch_size": 100}, "batch_by_time"
        )

        print(f"Task: {dag.root_task_id}")
        print(f"Subtasks: {len(dag.subtasks)}")

        # Create agent pool
        pool = AgentPool()

        # Execute DAG
        result = await pool.execute_dag(dag)

        print(f"\nResult: {result.get('count', 0)} items")

        # Verify
        verifier = VerificationEngine(pool)
        for st in dag.subtasks.values():
            vr = await verifier.verify_output(st.output, st)
            print(f"  {st.subtask_id}: {vr.is_valid} ({vr.score:.2f}) - {vr.reason}")

    asyncio.run(main())
