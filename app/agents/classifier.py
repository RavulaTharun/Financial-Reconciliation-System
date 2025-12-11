import pandas as pd
from typing import Dict, Any, List, Set
from datetime import datetime

from langchain_core.tools import tool

from app.core.config import config
from app.core.utils import (
    get_agent_logger,
    create_agent_log,
    save_agent_log
)

logger = get_agent_logger("classifier")

@tool
def classify_exception_tool(record: dict, match_status: str) -> str:
    """Classify a reconciliation exception based on match status and record data."""
    return f"Classifying exception for record with status: {match_status}"

class ClassifierAgent:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.agent_name = "classifier"
    
    def classify_bank_exceptions(self, bank_df: pd.DataFrame, 
                                  matched_df: pd.DataFrame) -> pd.DataFrame:
        classified = matched_df.copy()
        
        if 'exception_type' not in classified.columns:
            classified['exception_type'] = None
        
        for idx, row in classified.iterrows():
            if row.get('match_status') == 'No Match':
                bank_invoice = row.get('bank_invoice')
                
                if pd.isna(bank_invoice) or bank_invoice is None:
                    classified.loc[idx, 'exception_type'] = 'Non-Invoice Item'
                else:
                    classified.loc[idx, 'exception_type'] = 'Missing in ERP'
            
            elif row.get('match_confidence', 1.0) < config.CONFIDENCE_THRESHOLD_HUMAN_REVIEW:
                classified.loc[idx, 'exception_type'] = 'Manual Review Required'
        
        return classified
    
    def classify_erp_exceptions(self, erp_df: pd.DataFrame, 
                                 used_erp_ids: Set) -> pd.DataFrame:
        erp_classified = erp_df.copy()
        erp_classified['exception_type'] = None
        erp_classified['matched'] = False
        
        for idx, row in erp_classified.iterrows():
            erp_row_id = row.get('erp_row_id')
            if erp_row_id in used_erp_ids:
                erp_classified.loc[idx, 'matched'] = True
            else:
                erp_classified.loc[idx, 'exception_type'] = 'Missing in Bank'
        
        return erp_classified
    
    def run(self, bank_df: pd.DataFrame, erp_df: pd.DataFrame,
            matched_df: pd.DataFrame, used_erp_ids: Set,
            llm_client=None) -> Dict[str, Any]:
        start_time = datetime.now()
        logger.info(f"[AGENT:{self.agent_name}] START run_id={self.run_id} inputs=matched_rows:{len(matched_df)}, erp_rows:{len(erp_df)}")
        
        try:
            non_invoice_df = bank_df[bank_df.get('is_non_invoice', False) == True].copy() if 'is_non_invoice' in bank_df.columns else pd.DataFrame()
            
            if len(non_invoice_df) > 0:
                non_invoice_df['match_status'] = 'Non-Invoice'
                non_invoice_df['exception_type'] = 'Non-Invoice Item'
                non_invoice_df['match_confidence'] = 1.0
                non_invoice_df['explanation'] = non_invoice_df.apply(
                    lambda x: f"Non-invoice item: {x.get('non_invoice_type', 'Unknown')} - ${x.get('amount', 0):.2f}",
                    axis=1
                )
            
            classified_matches = self.classify_bank_exceptions(bank_df, matched_df)
            classified_erp = self.classify_erp_exceptions(erp_df, used_erp_ids)
            
            stats = {
                'missing_in_erp': len(classified_matches[classified_matches['exception_type'] == 'Missing in ERP']),
                'missing_in_bank': len(classified_erp[classified_erp['exception_type'] == 'Missing in Bank']),
                'non_invoice_items': len(non_invoice_df),
                'manual_review': len(classified_matches[classified_matches['exception_type'] == 'Manual Review Required']),
                'total_exceptions': 0
            }
            stats['total_exceptions'] = sum([
                stats['missing_in_erp'],
                stats['missing_in_bank'],
                stats['non_invoice_items'],
                stats['manual_review']
            ])
            
            top_discrepancies = self._get_top_discrepancies(
                classified_matches, classified_erp, non_invoice_df
            )
            
            llm_reasoning = self._generate_reasoning(
                classified_matches, classified_erp, non_invoice_df, stats, llm_client
            )
            
            result = {
                'success': True,
                'classified_matches': classified_matches,
                'classified_erp': classified_erp,
                'non_invoice_items': non_invoice_df,
                'statistics': stats,
                'top_discrepancies': top_discrepancies
            }
            
            log_entry = create_agent_log(
                run_id=self.run_id,
                agent_name=self.agent_name,
                input_summary=f"Matched rows: {len(matched_df)}, ERP rows: {len(erp_df)}",
                deterministic_output=stats,
                llm_reasoning=llm_reasoning,
                decision=f"Classification completed: {stats['total_exceptions']} total exceptions identified",
                confidence=0.95,
                rule_fired="exception_classification"
            )
            save_agent_log(self.run_id, self.agent_name, log_entry)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"[AGENT:{self.agent_name}] END run_id={self.run_id} summary=Classified {stats['total_exceptions']} exceptions in {duration:.2f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"[AGENT:{self.agent_name}] ERROR run_id={self.run_id} error={str(e)}")
            return {
                'success': False,
                'error': str(e),
                'statistics': {}
            }
    
    def _get_top_discrepancies(self, classified_matches: pd.DataFrame,
                               classified_erp: pd.DataFrame,
                               non_invoice_df: pd.DataFrame,
                               limit: int = 10) -> List[Dict]:
        discrepancies = []
        
        missing_erp = classified_matches[classified_matches['exception_type'] == 'Missing in ERP']
        for _, row in missing_erp.head(limit // 3).iterrows():
            discrepancies.append({
                'type': 'Missing in ERP',
                'invoice': row.get('bank_invoice'),
                'amount': row.get('bank_amount'),
                'date': row.get('bank_date'),
                'source': 'Bank'
            })
        
        missing_bank = classified_erp[classified_erp['exception_type'] == 'Missing in Bank']
        for _, row in missing_bank.head(limit // 3).iterrows():
            discrepancies.append({
                'type': 'Missing in Bank',
                'invoice': row.get('invoice_id'),
                'amount': row.get('amount'),
                'date': row.get('date'),
                'source': 'ERP'
            })
        
        for _, row in non_invoice_df.head(limit // 3).iterrows():
            discrepancies.append({
                'type': 'Non-Invoice',
                'description': row.get('description'),
                'amount': row.get('amount'),
                'date': row.get('date'),
                'source': 'Bank'
            })
        
        return discrepancies[:limit]
    
    def _generate_reasoning(self, classified_matches: pd.DataFrame,
                           classified_erp: pd.DataFrame,
                           non_invoice_df: pd.DataFrame,
                           stats: Dict, llm_client=None) -> str:
        reasoning = f"""Exception Classification Analysis:

1. Exception Summary:
   - Missing in ERP: {stats['missing_in_erp']} (Bank transactions with no ERP match)
   - Missing in Bank: {stats['missing_in_bank']} (ERP records with no Bank match)
   - Non-Invoice Items: {stats['non_invoice_items']} (Bank fees, adjustments, interest)
   - Manual Review Required: {stats['manual_review']} (Low confidence matches)
   - Total Exceptions: {stats['total_exceptions']}

2. Classification Logic:
   - 'Missing in ERP': Bank transaction has invoice ID but no ERP match found
   - 'Missing in Bank': ERP record not matched to any bank transaction
   - 'Non-Invoice Item': Bank transaction without invoice ID (fees, adjustments)
   - 'Manual Review': Match confidence below {config.CONFIDENCE_THRESHOLD_HUMAN_REVIEW}

3. Recommendations:
   - Investigate 'Missing in ERP' items for potential data entry gaps
   - Verify 'Missing in Bank' items for timing differences or errors
   - Non-invoice items should be reconciled separately
   - Manual review items require human verification
"""
        return reasoning
