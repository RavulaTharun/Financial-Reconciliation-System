import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_API_URL: str = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.1-70b-versatile")
    VECTOR_DB: str = os.getenv("VECTOR_DB", "chroma")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    
    AMOUNT_ROUNDING_TOLERANCE: float = 0.01
    FUZZY_AMOUNT_ABS: float = 1.0
    FUZZY_DATE_DAYS: int = 3
    CONFIDENCE_THRESHOLD_HUMAN_REVIEW: float = 0.6
    
    BANK_PDF_PATH: str = "data/bank_statement.pdf"
    ERP_EXCEL_PATH: str = "data/erp_data.xlsx"
    OUTPUT_DIR: str = "app/outputs"
    RESULTS_DIR: str = "app/outputs/results"
    LOGS_DIR: str = "app/outputs/logs"

config = Config()
