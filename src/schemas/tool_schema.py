# src/schemas/tool_schema.py
from typing import Callable, Type
from pydantic import BaseModel, ConfigDict, ValidationError


class WikiTool(BaseModel):
    """Ein Werkzeug, das ein WikiAgent im Rahmen einer ReAct-Schleife aufrufen kann.

    'parameters' beschreibt die erwarteten Argumente als Pydantic-Modell (daraus wird
    das JSON-Schema fürs Function-Calling erzeugt). 'func' ist der tatsächliche Python-
    Aufruf, der mit den validierten Argumenten als Keyword-Argumente ausgeführt wird
    und dessen Ergebnis als String an das LLM zurückgegeben wird.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    parameters: Type[BaseModel]
    func: Callable[..., str]

    def to_openai_schema(self) -> dict:
        """Function-Calling-Schema im von litellm/OpenAI erwarteten Format."""
        schema = self.parameters.model_json_schema()
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }

    def call(self, arguments: dict) -> str:
        """Führt das Tool aus und gibt IMMER einen String zurück (auch im Fehlerfall),
        damit das Ergebnis direkt als Tool-Nachricht ans LLM zurückgehen kann."""
        try:
            valid_args = self.parameters.model_validate(arguments)
        except ValidationError as e:
            return f"Fehler: Ungültige Argumente für Tool '{self.name}': {e}"

        try:
            result = self.func(**valid_args.model_dump())
        except Exception as e:
            return f"Fehler bei Ausführung von Tool '{self.name}': {e}"

        return result if isinstance(result, str) else str(result)
