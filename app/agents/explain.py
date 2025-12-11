import pandas as pd
from typing import Dict, Any, List
from datetime import datetime

from langchain_core.tools import tool

from app.core.config import config
from app.core.utils import (
    get_agent_logger,
    create_agent_log,
    save_agent_log
)

logger = get_agent_logger("explain")

@tool
def generate_explanation_tool(match_record: dict) -> str:
    """Generate a human-readable explanation for a reconciliation match decision."""
    return f"Generating explanation for match: {match_record.get('match_status', 'Unknown')}"

class ExplainAgent:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.agent_name = "explain"
    
    def generate_row_explanation(self, row: pd.Series) -> str:
        from app.core.llm_client import llm_client as llm
        
        match_status = row.get('match_status', 'Unknown')
        confidence = row.get('match_confidence', 0)
        invoice = row.get('bank_invoice', 'N/A')
        amount = row.get('bank_amount', 0)
        
        base_explanation = ""
        
        if match_status == 'Exact Match':
            base_explanation = f"Invoice {invoice} (${amount:.2f}) matched exactly with ERP record. High confidence match."
        
        elif match_status == 'Rounding Difference':
            diff = row.get('amount_difference', 0)
            base_explanation = f"Invoice {invoice} matched with ${diff:.4f} rounding difference. This is within acceptable tolerance."
        
        elif match_status == 'Probable Match':
            base_explanation = f"Invoice {invoice} (${amount:.2f}) is a probable match with {confidence:.0%} confidence. Manual verification recommended."
            
            if llm and llm.model:
                try:
                    bank_data = {"invoice": invoice, "amount": amount, "date": row.get('bank_date')}
                    erp_data = row.get('erp_data', {})
                    llm_explanation = llm.explain_match(bank_data, erp_data, match_status, confidence)
                    base_explanation += f" AI Analysis: {llm_explanation}"
                except Exception:
                    pass
        
        elif match_status == 'No Match':
            exception_type = row.get('exception_type', 'Unknown')
            if exception_type == 'Missing in ERP':
                base_explanation = f"Invoice {invoice} (${amount:.2f}) from bank has no matching ERP record. Investigate for missing ERP entry."
            elif exception_type == 'Non-Invoice Item':
                base_explanation = f"Bank transaction (${amount:.2f}) is a non-invoice item (fee/adjustment). Excluded from invoice reconciliation."
            else:
                base_explanation = f"Invoice {invoice} could not be matched. Requires manual investigation."
        
        elif match_status == 'Non-Invoice':
            base_explanation = f"Non-invoice bank item: {row.get('non_invoice_type', 'Unknown')} of ${amount:.2f}"
        
        else:
            base_explanation = f"Transaction status: {match_status}"
        
        return base_explanation
    
    def generate_summary(self, stats: Dict, match_stats: Dict, 
                        exception_stats: Dict) -> str:
        total_bank = stats.get('total_bank_transactions', 0)
        total_erp = stats.get('total_erp_records', 0)
        
        total_matched = match_stats.get('exact_matches', 0) + match_stats.get('rounding_matches', 0) + match_stats.get('fuzzy_matches', 0)
        match_rate = (total_matched / total_bank * 100) if total_bank > 0 else 0
        
        summary = f"""
FINANCIAL RECONCILIATION SUMMARY REPORT
========================================

OVERVIEW
--------
This reconciliation was performed using an AI-powered agentic workflow that automatically:
1. Ingested and parsed the Bank Statement PDF
2. Ingested and normalized the ERP Excel data
3. Detected and flagged duplicate transactions
4. Performed multi-tier matching (exact, rounding, fuzzy)
5. Classified exceptions and discrepancies
6. Generated explanations for each match decision

DATA SUMMARY
------------
- Bank Transactions Processed: {total_bank}
- ERP Records Processed: {total_erp}
- Invoice Transactions (Bank): {stats.get('bank_invoice_count', 0)}
- Non-Invoice Items (Bank): {stats.get('bank_non_invoice_count', 0)}

MATCHING RESULTS
----------------
- Exact Matches: {match_stats.get('exact_matches', 0)}
- Rounding Difference Matches: {match_stats.get('rounding_matches', 0)}
- Fuzzy/Probable Matches: {match_stats.get('fuzzy_matches', 0)}
- Unmatched Transactions: {match_stats.get('no_match', 0)}

OVERALL MATCH RATE: {match_rate:.1f}%

EXCEPTIONS IDENTIFIED
---------------------
- Missing in ERP: {exception_stats.get('missing_in_erp', 0)}
- Missing in Bank: {exception_stats.get('missing_in_bank', 0)}
- Non-Invoice Items: {exception_stats.get('non_invoice_items', 0)}
- Manual Review Required: {exception_stats.get('manual_review', 0)}

MATCHING THRESHOLDS USED
------------------------
- Rounding Tolerance: ${config.AMOUNT_ROUNDING_TOLERANCE}
- Fuzzy Amount Tolerance: ${config.FUZZY_AMOUNT_ABS}
- Fuzzy Date Tolerance: {config.FUZZY_DATE_DAYS} days
- Manual Review Threshold: {config.CONFIDENCE_THRESHOLD_HUMAN_REVIEW}

RECOMMENDATIONS
---------------
1. Review all 'Missing in ERP' items for potential data entry gaps
2. Verify 'Missing in Bank' items for timing differences or errors
3. Manually verify all low-confidence fuzzy matches
4. Non-invoice items (fees, adjustments) should be reconciled separately
5. Investigate duplicate transactions for potential double-posting

AI AGENT WORKFLOW
-----------------
This reconciliation was performed by the following AI agents:
1. BankIngestAgent - Parsed and normalized bank statement PDF
2. ERPIngestAgent - Parsed and normalized ERP Excel data
3. DedupeAgent - Detected duplicate transactions in both sources
4. MatcherAgent - Performed exact, rounding, and fuzzy matching
5. ClassifierAgent - Classified exceptions and discrepancies
6. ExplainAgent - Generated human-readable explanations

All agent decisions and reasoning are logged for audit purposes.
"""
        return summary
    
    def run(self, classified_matches: pd.DataFrame, stats: Dict,
            match_stats: Dict, exception_stats: Dict,
            llm_client=None) -> Dict[str, Any]:
        start_time = datetime.now()
        logger.info(f"[AGENT:{self.agent_name}] START run_id={self.run_id}")
        
        try:
            explained_df = classified_matches.copy()
            explained_df['ai_explanation'] = explained_df.apply(
                self.generate_row_explanation, axis=1
            )
            
            summary_report = self.generate_summary(stats, match_stats, exception_stats)
            
            llm_reasoning = f"""Explanation Generation Complete:
- Generated individual explanations for {len(explained_df)} transactions
- Created comprehensive summary report
- All explanations follow consistent templating for clarity
- Recommendations provided based on exception analysis
"""
            
            result = {
                'success': True,
                'explained_data': explained_df,
                'summary_report': summary_report
            }
            
            log_entry = create_agent_log(
                run_id=self.run_id,
                agent_name=self.agent_name,
                input_summary=f"Classified matches: {len(classified_matches)}",
                deterministic_output={'explanations_generated': len(explained_df)},
                llm_reasoning=llm_reasoning,
                decision="Explanations generated successfully",
                confidence=0.95,
                rule_fired="template_explanation"
            )
            save_agent_log(self.run_id, self.agent_name, log_entry)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"[AGENT:{self.agent_name}] END run_id={self.run_id} summary=Generated explanations in {duration:.2f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"[AGENT:{self.agent_name}] ERROR run_id={self.run_id} error={str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
