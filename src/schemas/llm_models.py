# src/schemas/enums.py
from enum import StrEnum

class LLMModels(StrEnum):
    """Models available to the system."""
    GEMINI_3_5_FLASH_LITE = "gemini/gemini-3.5-flash-lite"
    GEMINI_3_1_FLASH_LITE = "gemini/gemini-3.1-flash-lite"
    GEMMA_31B = "gemini/gemma-4-31b-it"
    GEMMA_26B = "gemini/gemma-4-26b-a4b-it"




TOOL_MODELS: tuple[LLMModels, ...] = (
    LLMModels.GEMINI_3_5_FLASH_LITE,
    LLMModels.GEMINI_3_1_FLASH_LITE,
)

# Tool-specific fallbacks that rotate across capable models
TOOL_FALLBACK_MAP: dict[LLMModels, list[LLMModels]] = {
    LLMModels.GEMINI_3_5_FLASH_LITE: [LLMModels.GEMINI_3_1_FLASH_LITE],
    LLMModels.GEMINI_3_1_FLASH_LITE: [LLMModels.GEMINI_3_5_FLASH_LITE],
    LLMModels.GEMMA_31B: [LLMModels.GEMMA_26B, LLMModels.GEMINI_3_5_FLASH_LITE, LLMModels.GEMINI_3_1_FLASH_LITE],
    LLMModels.GEMMA_26B: [LLMModels.GEMMA_31B, LLMModels.GEMINI_3_5_FLASH_LITE, LLMModels.GEMINI_3_1_FLASH_LITE],
}

# Whichever model is started with, the cascade falls downwards from there (for non-tool / text-only turns).
FALLBACK_MAP = {
    LLMModels.GEMINI_3_5_FLASH_LITE: [
        LLMModels.GEMINI_3_1_FLASH_LITE, 
        LLMModels.GEMMA_31B, 
        LLMModels.GEMMA_26B
    ],
    LLMModels.GEMINI_3_1_FLASH_LITE: [
        LLMModels.GEMMA_31B, 
        LLMModels.GEMMA_26B
    ],
    LLMModels.GEMMA_31B: [
        LLMModels.GEMMA_26B
    ],
    LLMModels.GEMMA_26B: []  # Weakest model, no further fallback
}


def get_fallback_models(model: LLMModels | str, offer_tools: bool = False) -> list[LLMModels]:
    """Returns the fallback models for a given model.

    If offer_tools is True (tool calls are present), rotates across all possible
    fallback models that support tool calls instead of degrading to non-tool models.
    """
    try:
        model_enum = LLMModels(model)
    except ValueError:
        return []

    if offer_tools:
        if model_enum in TOOL_MODELS:
            idx = TOOL_MODELS.index(model_enum)
            return list(TOOL_MODELS[idx + 1:] + TOOL_MODELS[:idx])
        return TOOL_FALLBACK_MAP.get(model_enum, [m for m in TOOL_MODELS if m != model_enum])

    return FALLBACK_MAP.get(model_enum, [])