# src/schemas/task_agent_schema.py
from pydantic import BaseModel, Field


class TaskAgentInput(BaseModel):
    task_id: str = Field(description="Your own task ID - pass it as a reference on every update_plan call.")
    task: str = Field(description="The complete description of the assignment.")
    ai_map: str = Field(description="Overview of all files and folders in the vault with short summaries, the starting point for the work.")


class TaskAgentOutput(BaseModel):
    summary: str = Field(
        description="Final report: what was concretely done (including the vault paths actually used), "
                     "and what could not be completed and why."
    )


__all__ = [
    "TaskAgentInput",
    "TaskAgentOutput",
]
