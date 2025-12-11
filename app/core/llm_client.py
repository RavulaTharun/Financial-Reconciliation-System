import os
from typing import Optional, Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent

from app.core.config import config
from app.core.utils import get_agent_logger, truncate_text

logger = get_agent_logger("llm_client")

class LLMClient:
    def __init__(self):
        self.model = None
        self._initialize()
    
    def _initialize(self):
        api_key = config.GROQ_API_KEY
        
        if api_key:
            try:
                self.model = ChatOpenAI(
                    api_key=api_key,
                    base_url=config.GROQ_API_URL,
                    model=config.LLM_MODEL,
                    temperature=0.1,
                    max_tokens=1000
                )
                logger.info("[LLM] Initialized with Groq API")
            except Exception as e:
                logger.warning(f"[LLM] Failed to initialize Groq client: {e}")
                self.model = None
        else:
            logger.warning("[LLM] No API key configured, using rule-based fallback")
            self.model = None
    
    def invoke(self, prompt: str, system_prompt: str = None) -> str:
        if self.model is None:
            return self._fallback_reasoning(prompt)
        
        try:
            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=prompt))
            
            response = self.model.invoke(messages)
            return response.content
        except Exception as e:
            logger.warning(f"[LLM] API call failed: {e}, using fallback")
            return self._fallback_reasoning(prompt)
    
    def _fallback_reasoning(self, prompt: str) -> str:
        return f"[Rule-based analysis] Processed input data using deterministic matching rules. LLM reasoning unavailable - configure GROQ_API_KEY for AI-powered analysis."
    
    def analyze_bank_transaction(self, transaction_data: Dict) -> str:
        prompt = f"""Analyze this bank transaction and provide a brief assessment:
Transaction: {transaction_data}

Provide:
1. Transaction type classification
2. Any anomalies or concerns
3. Confidence in the classification (0-1)

Respond in 2-3 sentences."""
        
        return self.invoke(prompt, "You are a financial data analyst reviewing bank transactions.")
    
    def explain_match(self, bank_row: Dict, erp_row: Dict, match_type: str, confidence: float) -> str:
        prompt = f"""Explain this reconciliation match decision:
Bank Transaction: {bank_row}
ERP Record: {erp_row}
Match Type: {match_type}
Confidence: {confidence}

Provide a one-sentence human-readable explanation of why these records were matched (or not matched)."""
        
        return self.invoke(prompt, "You are a financial reconciliation expert explaining match decisions.")
    
    def classify_exception(self, record: Dict, exception_type: str) -> str:
        prompt = f"""Classify this reconciliation exception:
Record: {record}
Exception Type: {exception_type}

Provide:
1. Root cause analysis (1 sentence)
2. Recommended action (1 sentence)
3. Priority level (High/Medium/Low)"""
        
        return self.invoke(prompt, "You are a financial auditor reviewing reconciliation exceptions.")
    
    def generate_summary(self, stats: Dict) -> str:
        prompt = f"""Generate an executive summary for this financial reconciliation:
Statistics: {stats}

Provide a 3-4 sentence summary covering:
1. Overall reconciliation health
2. Key findings
3. Recommendations"""
        
        return self.invoke(prompt, "You are a CFO receiving a reconciliation report. Be concise and actionable.")

llm_client = LLMClient()
