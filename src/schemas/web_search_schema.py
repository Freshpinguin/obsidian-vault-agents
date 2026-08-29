# src/schemas/web_search_schema.py
from pydantic import BaseModel, Field


class WebSearchArgs(BaseModel):
    query: str = Field(
        description="Die Frage oder das zu recherchierende Konzept, möglichst konkret und in sich "
                     "verständlich formuliert (wird per echter Google-Websuche beantwortet)."
    )
