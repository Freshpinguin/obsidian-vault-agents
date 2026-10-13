# src/schemas/reasoner_schema.py
from pydantic import BaseModel, Field


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
