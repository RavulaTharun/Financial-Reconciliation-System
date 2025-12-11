import re
import json
from datetime import datetime
from typing import Any, Dict, Optional
from loguru import logger
import sys

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[agent]}</cyan> | <level>{message}</level>",
    level="DEBUG",
    colorize=True
)
logger.add(
    "app/outputs/logs/reconciliation_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="7 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[agent]} | {message}"
)

def get_agent_logger(agent_name: str):
    return logger.bind(agent=agent_name)

def normalize_amount(amount: Any) -> float:
    if amount is None:
        return 0.0
    if isinstance(amount, str):
        amount = amount.replace(",", "").replace("$", "").strip()
        try:
            return round(float(amount), 2)
        except ValueError:
            return 0.0
    return round(float(amount), 2)

def normalize_date(date_val: Any) -> Optional[str]:
    if date_val is None:
        return None
    if isinstance(date_val, datetime):
        return date_val.strftime("%Y-%m-%d")
    if isinstance(date_val, str):
        date_val = date_val.strip()
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]:
            try:
                return datetime.strptime(date_val, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return str(date_val)

def extract_invoice_id(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r'INV\d+', str(text), re.IGNORECASE)
    return match.group(0).upper() if match else None

def truncate_text(text: str, max_length: int = 2000) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + "... [TRUNCATED]"

def create_agent_log(
    run_id: str,
    agent_name: str,
    input_summary: str,
    deterministic_output: Any = None,
    llm_reasoning: str = "",
    decision: str = "",
    confidence: float = 0.0,
    rule_fired: str = ""
) -> Dict[str, Any]:
    return {
        "timestamp": datetime.now().isoformat(),
        "run_id": run_id,
        "agent_name": agent_name,
        "input_summary": truncate_text(str(input_summary)),
        "deterministic_output": deterministic_output,
        "llm_reasoning": truncate_text(llm_reasoning),
        "decision": decision,
        "confidence": confidence,
        "rule_fired": rule_fired
    }

def save_agent_log(run_id: str, agent_name: str, log_data: Dict[str, Any]):
    import os
    os.makedirs("app/outputs/logs", exist_ok=True)
    log_file = f"app/outputs/logs/{run_id}_agent_{agent_name}.json"
    logs = []
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []
    logs.append(log_data)
    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2, default=str)
