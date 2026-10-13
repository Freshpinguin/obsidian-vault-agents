from pydantic import BaseModel, Field
import pytest

from src.schemas.tool_schema import WikiTool


class DummyParams(BaseModel):
    query: str = Field(description="Search term")
    limit: int = Field(default=5, description="Max results")


def test_tool_to_openai_schema():
    tool = WikiTool(
        name="dummy_tool",
        description="A dummy test tool",
        parameters=DummyParams,
        func=lambda query, limit=5: f"Found {limit} for {query}",
    )
    schema = tool.to_openai_schema()
    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == "dummy_tool"
    assert fn["description"] == "A dummy test tool"
    params = fn["parameters"]
    assert "title" not in params
    assert "title" not in params["properties"]["query"]
    assert "title" not in params["properties"]["limit"]


def test_tool_call_valid_arguments():
    tool = WikiTool(
        name="dummy_tool",
        description="A dummy test tool",
        parameters=DummyParams,
        func=lambda query, limit=5: f"Result: {query} ({limit})",
    )
    res = tool.call({"query": "Alpha", "limit": 3})
    assert res == "Result: Alpha (3)"


def test_tool_call_invalid_arguments():
    tool = WikiTool(
        name="dummy_tool",
        description="A dummy test tool",
        parameters=DummyParams,
        func=lambda query, limit=5: f"Result: {query}",
    )
    # Missing required 'query'
    res = tool.call({"limit": "not_an_int"})
    assert "Error: invalid arguments for tool 'dummy_tool'" in res


def test_tool_call_function_raises_exception():
    def _exploding_func(query: str, limit: int = 5):
        raise RuntimeError("Something exploded")

    tool = WikiTool(
        name="exploding_tool",
        description="Boom",
        parameters=DummyParams,
        func=_exploding_func,
    )
    res = tool.call({"query": "explode"})
    assert "Error executing tool 'exploding_tool': Something exploded" in res


def test_tool_call_non_string_return_converted_to_str():
    tool = WikiTool(
        name="num_tool",
        description="Returns number",
        parameters=DummyParams,
        func=lambda query, limit=5: 12345,
    )
    res = tool.call({"query": "num"})
    assert res == "12345"
    assert isinstance(res, str)
