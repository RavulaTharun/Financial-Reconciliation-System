import os
import json
import pandas as pd
from typing import Dict, Any, TypedDict, Annotated
from datetime import datetime
from operator import add

from langgraph.graph import StateGraph, END

from app.core.config import config
from app.core.utils import get_agent_logger, save_agent_log, create_agent_log
from app.core.storage import run_storage
from app.agents.ingest_bank import BankIngestAgent
from app.agents.ingest_erp import ERPIngestAgent
from app.agents.dedupe import DedupeAgent
from app.agents.matcher import MatcherAgent
from app.agents.classifier import ClassifierAgent
from app.agents.explain import ExplainAgent

logger = get_agent_logger("orchestrator")

class ReconciliationState(TypedDict):
    run_id: str
    status: str
    current_step: str
    bank_data: Any
    erp_data: Any
    dedupe_result: Any
    match_result: Any
    classification_result: Any
    explanation_result: Any
    errors: list
    steps_completed: list

def create_initial_state(run_id: str) -> ReconciliationState:
    return {
        "run_id": run_id,
        "status": "initialized",
        "current_step": "",
        "bank_data": None,
        "erp_data": None,
        "dedupe_result": None,
        "match_result": None,
        "classification_result": None,
        "explanation_result": None,
        "errors": [],
        "steps_completed": []
    }

def ingest_bank_node(state: ReconciliationState) -> Dict[str, Any]:
    run_id = state["run_id"]
    logger.info(f"[ORCHESTRATOR] Executing ingest_bank node for run_id={run_id}")
    
    run_storage.update_run(run_id, current_step="ingest_bank", progress=10)
    
    agent = BankIngestAgent(run_id)
    result = agent.run()
    
    if result["success"]:
        return {
            "bank_data": result,
            "current_step": "ingest_bank_complete",
            "steps_completed": ["ingest_bank"]
        }
    else:
        return {
            "errors": [f"Bank ingest failed: {result.get('error', 'Unknown error')}"],
            "status": "failed"
        }

def ingest_erp_node(state: ReconciliationState) -> Dict[str, Any]:
    run_id = state["run_id"]
    logger.info(f"[ORCHESTRATOR] Executing ingest_erp node for run_id={run_id}")
    
    run_storage.update_run(run_id, current_step="ingest_erp", progress=20)
    
    agent = ERPIngestAgent(run_id)
    result = agent.run()
    
    if result["success"]:
        return {
            "erp_data": result,
            "current_step": "ingest_erp_complete",
            "steps_completed": ["ingest_erp"]
        }
    else:
        return {
            "errors": [f"ERP ingest failed: {result.get('error', 'Unknown error')}"],
            "status": "failed"
        }

def dedupe_node(state: ReconciliationState) -> Dict[str, Any]:
    run_id = state["run_id"]
    logger.info(f"[ORCHESTRATOR] Executing dedupe node for run_id={run_id}")
    
    run_storage.update_run(run_id, current_step="dedupe", progress=35)
    
    if state.get("bank_data") is None or state.get("erp_data") is None:
        return {
            "errors": ["Bank or ERP data not available"],
            "status": "failed"
        }
    
    bank_df = state["bank_data"]["data"]
    erp_df = state["erp_data"]["data"]
    
    agent = DedupeAgent(run_id)
    result = agent.run(bank_df, erp_df)
    
    if result["success"]:
        return {
            "dedupe_result": result,
            "current_step": "dedupe_complete",
            "steps_completed": ["dedupe"]
        }
    else:
        return {
            "errors": [f"Dedupe failed: {result.get('error', 'Unknown error')}"],
            "status": "failed"
        }

def matcher_node(state: ReconciliationState) -> Dict[str, Any]:
    run_id = state["run_id"]
    logger.info(f"[ORCHESTRATOR] Executing matcher node for run_id={run_id}")
    
    run_storage.update_run(run_id, current_step="matcher", progress=50)
    
    bank_df = state["dedupe_result"]["bank_data"]
    erp_df = state["dedupe_result"]["erp_data"]
    
    agent = MatcherAgent(run_id)
    result = agent.run(bank_df, erp_df)
    
    if result["success"]:
        return {
            "match_result": result,
            "current_step": "matcher_complete",
            "steps_completed": ["matcher"]
        }
    else:
        return {
            "errors": [f"Matching failed: {result.get('error', 'Unknown error')}"],
            "status": "failed"
        }

def classifier_node(state: ReconciliationState) -> Dict[str, Any]:
    run_id = state["run_id"]
    logger.info(f"[ORCHESTRATOR] Executing classifier node for run_id={run_id}")
    
    run_storage.update_run(run_id, current_step="classifier", progress=70)
    
    bank_df = state["dedupe_result"]["bank_data"]
    erp_df = state["dedupe_result"]["erp_data"]
    matched_df = state["match_result"]["matched_data"]
    used_erp_ids = state["match_result"]["used_erp_ids"]
    
    agent = ClassifierAgent(run_id)
    result = agent.run(bank_df, erp_df, matched_df, used_erp_ids)
    
    if result["success"]:
        return {
            "classification_result": result,
            "current_step": "classifier_complete",
            "steps_completed": ["classifier"]
        }
    else:
        return {
            "errors": [f"Classification failed: {result.get('error', 'Unknown error')}"],
            "status": "failed"
        }

def explain_node(state: ReconciliationState) -> Dict[str, Any]:
    run_id = state["run_id"]
    logger.info(f"[ORCHESTRATOR] Executing explain node for run_id={run_id}")
    
    run_storage.update_run(run_id, current_step="explain", progress=85)
    
    classified_matches = state["classification_result"]["classified_matches"]
    
    stats = {
        "total_bank_transactions": state["bank_data"]["total_rows"],
        "total_erp_records": state["erp_data"]["total_rows"],
        "bank_invoice_count": state["bank_data"]["invoice_count"],
        "bank_non_invoice_count": state["bank_data"]["non_invoice_count"]
    }
    match_stats = state["match_result"]["statistics"]
    exception_stats = state["classification_result"]["statistics"]
    
    agent = ExplainAgent(run_id)
    result = agent.run(classified_matches, stats, match_stats, exception_stats)
    
    if result["success"]:
        return {
            "explanation_result": result,
            "current_step": "explain_complete",
            "steps_completed": ["explain"]
        }
    else:
        return {
            "errors": [f"Explanation failed: {result.get('error', 'Unknown error')}"],
            "status": "failed"
        }

def output_node(state: ReconciliationState) -> Dict[str, Any]:
    run_id = state["run_id"]
    logger.info(f"[ORCHESTRATOR] Executing output node for run_id={run_id}")
    
    run_storage.update_run(run_id, current_step="output", progress=95)
    
    try:
        from app.agents.output_generator import OutputGenerator
        generator = OutputGenerator(run_id)
        
        result = generator.generate_all_outputs(
            explained_data=state["explanation_result"]["explained_data"],
            summary_report=state["explanation_result"]["summary_report"],
            classified_erp=state["classification_result"]["classified_erp"],
            non_invoice_items=state["classification_result"]["non_invoice_items"],
            match_stats=state["match_result"]["statistics"],
            exception_stats=state["classification_result"]["statistics"],
            bank_stats={
                "total_rows": state["bank_data"]["total_rows"],
                "invoice_count": state["bank_data"]["invoice_count"],
                "non_invoice_count": state["bank_data"]["non_invoice_count"]
            },
            erp_stats={
                "total_rows": state["erp_data"]["total_rows"]
            }
        )
        
        run_storage.update_run(
            run_id, 
            status="completed",
            progress=100,
            output_files=result.get("output_files", [])
        )
        
        return {
            "status": "completed",
            "current_step": "output_complete",
            "steps_completed": ["output"]
        }
        
    except Exception as e:
        logger.error(f"[ORCHESTRATOR] Output generation failed: {str(e)}")
        return {
            "errors": [f"Output generation failed: {str(e)}"],
            "status": "failed"
        }

def should_continue(state: ReconciliationState) -> str:
    if state.get("status") == "failed":
        return "end"
    return "continue"

def build_workflow():
    workflow = StateGraph(ReconciliationState)
    
    workflow.add_node("ingest_bank", ingest_bank_node)
    workflow.add_node("ingest_erp", ingest_erp_node)
    workflow.add_node("dedupe", dedupe_node)
    workflow.add_node("matcher", matcher_node)
    workflow.add_node("classifier", classifier_node)
    workflow.add_node("explain", explain_node)
    workflow.add_node("output", output_node)
    
    workflow.set_entry_point("ingest_bank")
    workflow.add_edge("ingest_bank", "ingest_erp")
    workflow.add_edge("ingest_erp", "dedupe")
    workflow.add_edge("dedupe", "matcher")
    workflow.add_edge("matcher", "classifier")
    workflow.add_edge("classifier", "explain")
    workflow.add_edge("explain", "output")
    workflow.add_edge("output", END)
    
    return workflow.compile()

class ReconciliationOrchestrator:
    def __init__(self):
        self.workflow = build_workflow()
    
    def run(self, run_id: str) -> Dict[str, Any]:
        logger.info(f"[ORCHESTRATOR] Starting reconciliation workflow for run_id={run_id}")
        
        run_storage.create_run(run_id)
        run_storage.update_run(run_id, status="running")
        
        initial_state = create_initial_state(run_id)
        
        try:
            final_state = None
            for state in self.workflow.stream(initial_state):
                final_state = state
                logger.debug(f"[ORCHESTRATOR] State update: {list(state.keys())}")
            
            log_entry = create_agent_log(
                run_id=run_id,
                agent_name="orchestrator",
                input_summary="Full reconciliation workflow",
                deterministic_output={"status": "completed"},
                llm_reasoning="Workflow completed successfully through all agent nodes",
                decision="Reconciliation complete",
                confidence=1.0,
                rule_fired="workflow_complete"
            )
            save_agent_log(run_id, "orchestrator", log_entry)
            
            logger.info(f"[ORCHESTRATOR] Workflow completed for run_id={run_id}")
            
            return run_storage.get_run(run_id)
            
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Workflow failed for run_id={run_id}: {str(e)}")
            run_storage.update_run(run_id, status="failed", errors=[str(e)])
            return run_storage.get_run(run_id)

orchestrator = ReconciliationOrchestrator()
