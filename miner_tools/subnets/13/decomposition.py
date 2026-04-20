#!/usr/bin/env python3
"""
Task Decomposition Engine for SN13 (Data Universe)

Converts validator task → DAG of subtasks
"""

from __future__ import annotations
import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"


class TaskType(Enum):
    GET_MINER_INDEX = "GetMinerIndex"
    GET_DATA_ENTITY_BUCKET = "GetDataEntityBucket"
    GET_CONTENTS_BY_BUCKETS = "GetContentsByBuckets"


@dataclass
class SubTask:
    """Single subtask in the DAG."""

    subtask_id: str
    task_type: str
    input_data: dict
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list = field(default_factory=list)
    assigned_agent: str | None = None
    output: dict | None = None
    verification_score: float = 0.0
    is_valid: bool = False
    reward: float = 0.0


@dataclass
class TaskDAG:
    """Task as Directed Acyclic Graph."""

    root_task_id: str
    task_type: TaskType
    input_data: dict
    subtasks: dict[str, SubTask] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_subtask(self, subtask: SubTask):
        self.subtasks[subtask.subtask_id] = subtask

    def get_ready_subtasks(self) -> list[SubTask]:
        """Get tasks ready to execute (all deps completed)."""
        ready = []
        for st in self.subtasks.values():
            if st.status != TaskStatus.PENDING:
                continue
            # Check if all dependencies are completed
            deps_ready = all(
                self.subtasks[dep].status == TaskStatus.COMPLETED for dep in st.dependencies
            )
            if deps_ready:
                ready.append(st)
        return ready

    def mark_completed(self, subtask_id: str, output: dict):
        """Mark subtask completed."""
        if subtask_id in self.subtasks:
            self.subtasks[subtask_id].status = TaskStatus.COMPLETED
            self.subtasks[subtask_id].output = output

    def get_result(self) -> dict:
        """Get aggregated result."""
        outputs = [st.output for st in self.subtasks.values() if st.output]
        if not outputs:
            return {}
        # Merge outputs based on task type
        if self.task_type == TaskType.GET_DATA_ENTITY_BUCKET:
            return self._aggregate_data_entities(outputs)
        return outputs[0] if outputs else {}

    def _aggregate_data_entities(self, outputs: list[dict]) -> dict:
        """Merge data entity outputs."""
        all_entities = []
        for out in outputs:
            entities = out.get("data", [])
            all_entities.extend(entities)
        return {"data": all_entities, "count": len(all_entities)}


class DecompositionEngine:
    """
    Converts validator task → DAG of subtasks.

    Strategies:
    - Template-based (MapReduce style)
    - Chunk by time
    - Chunk by label
    - Redundant execution for verification
    """

    # Default batch sizes
    DEFAULT_BATCH_SIZE = 100
    VERIFICATION_BATCH_SIZE = 10

    def __init__(self):
        self.strategies = {
            "batch_by_time": self._decompose_by_time,
            "batch_by_label": self._decompose_by_label,
            "redundant": self._decompose_redundant,
        }

    def decompose(
        self, task_type: str, input_data: dict, strategy: str = "batch_by_time"
    ) -> TaskDAG:
        """Convert task to DAG."""
        ttype = TaskType(task_type)

        # Create root task
        root_id = self._generate_task_id(task_type, input_data)
        dag = TaskDAG(
            root_task_id=root_id,
            task_type=ttype,
            input_data=input_data,
        )

        # Decompose based on type
        if ttype == TaskType.GET_MINER_INDEX:
            self._decompose_miner_index(dag, input_data)
        elif ttype == TaskType.GET_DATA_ENTITY_BUCKET:
            decomposer = self.strategies.get(strategy, self._decompose_by_time)
            decomposer(dag, input_data)
        elif ttype == TaskType.GET_CONTENTS_BY_BUCKETS:
            self._decompose_verification(dag, input_data)

        return dag

    def _decompose_miner_index(self, dag: TaskDAG, input_data: dict):
        """GetMinerIndex - no decomposition needed."""
        subtask = SubTask(
            subtask_id=f"{dag.root_task_id}_index",
            task_type="GetMinerIndex",
            input_data={},
            status=TaskStatus.READY,
            dependencies=[],
        )
        dag.add_subtask(subtask)

    def _decompose_by_time(self, dag: TaskDAG, input_data: dict):
        """
        Decompose by time chunks.
        Example: 1500 posts → 3 chunks of 500 each
        """
        bucket = input_data.get("data_entity_bucket_id", {})
        count = input_data.get("expected_count", self.DEFAULT_BATCH_SIZE)
        batch_size = input_data.get("batch_size", self.DEFAULT_BATCH_SIZE)

        # Split time into chunks
        num_chunks = (count + batch_size - 1) // batch_size

        for i in range(num_chunks):
            chunk_id = f"chunk_{i}"
            start_idx = i * batch_size
            end_idx = min((i + 1) * batch_size, count)

            subtask = SubTask(
                subtask_id=f"{dag.root_task_id}_{chunk_id}",
                task_type="scrape_time_chunk",
                input_data={
                    **bucket,
                    "start_idx": start_idx,
                    "end_idx": end_idx,
                    "chunk": i,
                    "total_chunks": num_chunks,
                },
                status=TaskStatus.READY,
                dependencies=[],
            )
            dag.add_subtask(subtask)

    def _decompose_by_label(self, dag: TaskDAG, input_data: dict):
        """
        Decompose by label (topic).
        Example: ["BTC", "ETH", "SOL"] → 3 parallel tasks
        """
        bucket = input_data.get("data_entity_bucket_id", {})
        labels = input_data.get("labels", [])

        for label in labels:
            subtask = SubTask(
                subtask_id=f"{dag.root_task_id}_label_{label}",
                task_type="scrape_label",
                input_data={**bucket, "label": label},
                status=TaskStatus.READY,
                dependencies=[],
            )
            dag.add_subtask(subtask)

    def _decompose_redundant(self, dag: TaskDAG, input_data: dict):
        """
        Decompose with redundancy for verification.
        Same task assigned to 2-3 agents, compare results.
        """
        redundancy = input_data.get("redundancy_count", 2)

        for i in range(redundancy):
            subtask = SubTask(
                subtask_id=f"{dag.root_task_id}_redundant_{i}",
                task_type="scrape_with_verify",
                input_data=input_data,
                status=TaskStatus.READY,
                dependencies=[],
            )
            dag.add_subtask(subtask)

    def _decompose_verification(self, dag: TaskDAG, input_data: dict):
        """GetContentsByBuckets - verification task."""
        bucket_ids = input_data.get("bucket_ids", [])
        sample_size = input_data.get("sample_size", self.VERIFICATION_BATCH_SIZE)

        for bucket_id in bucket_ids:
            subtask = SubTask(
                subtask_id=f"{dag.root_task_id}_verify_{bucket_id}",
                task_type="verify_bucket",
                input_data={
                    "bucket_id": bucket_id,
                    "sample_size": sample_size,
                },
                status=TaskStatus.READY,
                dependencies=[],
            )
            dag.add_subtask(subtask)

    def _generate_task_id(self, task_type: str, input_data: dict) -> str:
        """Generate unique task ID."""
        data_str = json.dumps(input_data, sort_keys=True)
        hash_str = hashlib.md5(data_str.encode()).hexdigest()[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{task_type}_{timestamp}_{hash_str}"


# Example usage
if __name__ == "__main__":
    engine = DecompositionEngine()

    # Example 1: Get data entity bucket task
    input_data = {
        "data_entity_bucket_id": {
            "source": "X",
            "time_bucket_id": 1845,
            "label": "$BTC",
        },
        "expected_count": 1500,
    }

    dag = engine.decompose("GetDataEntityBucket", input_data, strategy="batch_by_time")

    print(f"Task DAG: {dag.root_task_id}")
    print(f"Subtasks: {len(dag.subtasks)}")
    for st in dag.subtasks.values():
        print(f"  - {st.subtask_id}: {st.task_type} (status: {st.status.value})")

    # Simulate execution
    print("\n--- Execution ---")
    for st in dag.get_ready_subtasks():
        print(f"Execute: {st.subtask_id}")
        # Simulate work
        st.status = TaskStatus.COMPLETED
        st.output = {"data_entities": [{"content": f"Mock data {st.subtask_id}"}]}

    # Get result
    result = dag.get_result()
    print(f"\nAggregated result: {result}")
