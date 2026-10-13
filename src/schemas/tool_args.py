# src/schemas/tool_args.py
"""Pydantic models for all tool-call arguments."""
from typing import Literal
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    step: str = Field(description="Short description of this work step.")
    status: Literal["pending", "in_progress", "done"] = Field(description="Current status of this step.")


class AskLibrarianArgs(BaseModel):
    question: str = Field(description="The research question for the librarian, which searches the vault for it.")


class CreateDirectoryArgs(BaseModel):
    path: str = Field(description="Vault path of the folder to create (including any missing parent folders).")


class CreateFileArgs(BaseModel):
    path: str = Field(description="Vault path of the .md file to create (must not exist yet).")
    content: str = Field(description="Content of the new file (plain Markdown text, without frontmatter).")


class EditFileArgs(BaseModel):
    path: str = Field(description="Vault path of the existing .md file to edit.")
    content: str = Field(description="The NEW complete content of the file (entirely replaces the existing content below the frontmatter).")


class MoveFileArgs(BaseModel):
    path: str = Field(description="Vault path of the existing file to move/rename.")
    new_path: str = Field(description="New vault path of the file (must not exist yet, must end in .md).")


class DeleteFileArgs(BaseModel):
    path: str = Field(description="Vault path of the existing .md file to delete.")


class StartBackgroundTaskArgs(BaseModel):
    description: str = Field(
        description="Complete, self-contained description of the assignment for the task agent "
                     "(the task agent does not know the conversation so far, so fold in the relevant context)."
    )


class CheckTaskStatusArgs(BaseModel):
    task_id: str = Field(description="The task_id that start_background_task returned.")


class PathsArgs(BaseModel):
    paths: list[str] = Field(
        description="List of vault paths (folders or files). Always pass all relevant paths at once "
                     "instead of making several individual calls one after another."
    )


class UpdatePlanArgs(BaseModel):
    task_id: str = Field(description="Your own task ID.")
    steps: list[PlanStep] = Field(
        description="The COMPLETE current plan (all steps, not just new or changed ones), in "
                     "execution order."
    )


class WebSearchArgs(BaseModel):
    query: str = Field(
        description="The question or the concept to research, phrased as concretely and "
                     "self-containedly as possible (answered via a real Google web search)."
    )


class ReasoningArgs(BaseModel):
    task: str = Field(
        description="The task for the reasoning agent: a complex consideration or a text to draft, "
                     "phrased as concretely and self-containedly as possible (the agent does not know the "
                     "conversation so far, only what is written here)."
    )
    file_paths: list[str] = Field(
        default_factory=list,
        description="Optional vault paths whose content should be sent along as additional context "
                     "(e.g. existing notes the elaboration should build on).",
    )


__all__ = [
    "PlanStep",
    "AskLibrarianArgs",
    "CreateDirectoryArgs",
    "CreateFileArgs",
    "EditFileArgs",
    "MoveFileArgs",
    "DeleteFileArgs",
    "StartBackgroundTaskArgs",
    "CheckTaskStatusArgs",
    "PathsArgs",
    "UpdatePlanArgs",
    "WebSearchArgs",
    "ReasoningArgs",
]
