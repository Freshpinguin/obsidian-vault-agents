# src/schemas/enums.py
from enum import StrEnum

class LLMModels(StrEnum):
    """Verfügbare Modelle für das Wiki-System."""
    GEMINI_3_5_FLASH_LITE = "gemini/gemini-3.5-flash-lite"
    GEMINI_3_1_FLASH_LITE = "gemini/gemini-3.1-flash-lite"
    GEMMA_31B = "gemini/gemma-4-31b-it"
    GEMMA_26B = "gemini/gemma-4-26b-a4b-it"




# Egal bei welchem Modell gestartet wird, die Kaskade greift abwärts.
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
    LLMModels.GEMMA_26B: []  # Schwächstes Modell, kein 
    }