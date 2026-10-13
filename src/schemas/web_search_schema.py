# src/schemas/web_search_schema.py
from pydantic import BaseModel, Field


class WebSearchArgs(BaseModel):
    query: str = Field(
        description="The question or the concept to research, phrased as concretely and "
                     "self-containedly as possible (answered via a real Google web search)."
    )
