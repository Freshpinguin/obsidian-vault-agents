from src.schemas.llm_models import (
    FALLBACK_MAP,
    LLMModels,
    TOOL_FALLBACK_MAP,
    TOOL_MODELS,
    get_fallback_models,
)


def test_tool_fallback_models_rotation():
    # GEMINI_3_5_FLASH_LITE rotates to GEMINI_3_1_FLASH_LITE
    fallbacks_35 = get_fallback_models(LLMModels.GEMINI_3_5_FLASH_LITE, offer_tools=True)
    assert fallbacks_35 == [LLMModels.GEMINI_3_1_FLASH_LITE]

    # GEMINI_3_1_FLASH_LITE rotates to GEMINI_3_5_FLASH_LITE
    fallbacks_31 = get_fallback_models(LLMModels.GEMINI_3_1_FLASH_LITE, offer_tools=True)
    assert fallbacks_31 == [LLMModels.GEMINI_3_5_FLASH_LITE]


def test_non_tool_fallbacks_standard_cascade():
    # Without tools, standard downwards cascade applies
    fallbacks_35 = get_fallback_models(LLMModels.GEMINI_3_5_FLASH_LITE, offer_tools=False)
    assert fallbacks_35 == FALLBACK_MAP[LLMModels.GEMINI_3_5_FLASH_LITE]

    fallbacks_31 = get_fallback_models(LLMModels.GEMINI_3_1_FLASH_LITE, offer_tools=False)
    assert fallbacks_31 == FALLBACK_MAP[LLMModels.GEMINI_3_1_FLASH_LITE]


def test_gemma_tool_fallback_includes_tool_models():
    # When starting with a Gemma model during a tool turn, it rotates its peer then tool models
    fallbacks_gemma31 = get_fallback_models(LLMModels.GEMMA_31B, offer_tools=True)
    assert LLMModels.GEMINI_3_5_FLASH_LITE in fallbacks_gemma31
    assert LLMModels.GEMINI_3_1_FLASH_LITE in fallbacks_gemma31


def test_unknown_model_returns_empty():
    assert get_fallback_models("unknown_model", offer_tools=True) == []
    assert get_fallback_models("unknown_model", offer_tools=False) == []
