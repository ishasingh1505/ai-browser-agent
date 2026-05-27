"""
Planner Agent — Phase 4 skeleton.

In Phase 1 this is a simple passthrough that echoes the query as a single task.
Phase 4 will replace the body with a LangGraph-based multi-step orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResearchTask:
    step: int
    description: str
    tool: str                   # "search" | "visit" | "extract" | "compare" | "summarize"
    args: dict = field(default_factory=dict)
    result: dict | None = None
    status: str = "pending"     # pending | running | done | failed


class PlannerAgent:
    """
    Breaks a user query into an ordered list of ResearchTasks.

    Phase 1 — returns a single Search task.
    Phase 4 — will use an LLM + LangGraph to produce a full plan.
    """

    def create_plan(self, query: str) -> list[ResearchTask]:
        # Phase 1: trivial single-step plan
        return [
            ResearchTask(
                step=1,
                description=f"Search the web for: {query}",
                tool="search",
                args={"query": query},
            )
        ]
