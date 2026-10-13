# src/schemas/tool_schema.py
from typing import Callable, Type
from pydantic import BaseModel, ConfigDict, ValidationError


class WikiTool(BaseModel):
    """A tool that a WikiAgent can call as part of a ReAct loop.

    'parameters' describes the expected arguments as a Pydantic model (the JSON schema
    for function calling is generated from it). 'func' is the actual Python callable,
    executed with the validated arguments as keyword arguments, whose result is
    returned to the LLM as a string.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    parameters: Type[BaseModel]
    func: Callable[..., str]

    def to_openai_schema(self) -> dict:
        """Function-calling schema in the format litellm/OpenAI expects."""
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
        """Executes the tool and ALWAYS returns a string (including on failure), so
        the result can go straight back to the LLM as a tool message."""
        try:
            valid_args = self.parameters.model_validate(arguments)
        except ValidationError as e:
            return f"Error: invalid arguments for tool '{self.name}': {e}"

        try:
            result = self.func(**valid_args.model_dump())
        except Exception as e:
            return f"Error executing tool '{self.name}': {e}"

        return result if isinstance(result, str) else str(result)


MUTATION_TOOL_NAMES: frozenset[str] = frozenset({
    "create_file",
    "edit_file",
    "move_file",
    "create_directory",
    "delete_file",
})
