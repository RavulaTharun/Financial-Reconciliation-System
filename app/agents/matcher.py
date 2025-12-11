import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

from langchain_core.tools import tool

from app.core.config import config
from app.core.utils import (
    get_agent_logger,
    create_agent_log,
    save_agent_log
)

logger = get_agent_logger("matcher")

@tool
def exact_match_tool(bank_invoice: str, bank_amount: float, erp_records: list) -> str:
    """Find exact matches between bank transaction and ERP records by invoice ID and amount."""
    return f"Searching for exact match: {bank_invoice} with amount {bank_amount}"

@tool
def fuzzy_match_tool(bank_amount: float, bank_date: str, erp_records: list) -> str:
    """Find fuzzy matches based on amount proximity and date range."""
    return f"Searching for fuzzy match: amount {bank_amount} on date {bank_date}"

class MatcherAgent:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.agent_name = "matcher"
    
    def exact_match(self, bank_row: pd.Series, erp_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if pd.isna(bank_row.get('invoice_id')):
            return None
        
        invoice_id = str(bank_row['invoice_id']).upper()
        bank_amount = float(bank_row['amount'])
        
        matches = erp_df[
            (erp_df['invoice_id'].str.upper() == invoice_id) &
            (erp_df['amount'] == bank_amount)
        ]
        
        if len(matches) > 0:
            match_row = matches.iloc[0]
            return {
                'erp_row_id': match_row.get('erp_row_id'),
                'match_status': 'Exact Match',
                'match_confidence': 0.99,
                'rule_fired': 'exact_invoice_amount',
                'explanation': f"Invoice {invoice_id} matched exactly with amount ${bank_amount:.2f}",
                'erp_data': match_row.to_dict()
            }
        return None
    
    def rounding_match(self, bank_row: pd.Series, erp_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if pd.isna(bank_row.get('invoice_id')):
            return None
        
        invoice_id = str(bank_row['invoice_id']).upper()
        bank_amount = float(bank_row['amount'])
        
        matches = erp_df[erp_df['invoice_id'].str.upper() == invoice_id]
        
        for _, erp_row in matches.iterrows():
            erp_amount = float(erp_row['amount'])
            diff = abs(bank_amount - erp_amount)
            
            if diff <= config.AMOUNT_ROUNDING_TOLERANCE and diff > 0:
                return {
                    'erp_row_id': erp_row.get('erp_row_id'),
                    'match_status': 'Rounding Difference',
                    'match_confidence': 0.90,
                    'rule_fired': 'rounding_tolerance',
                    'explanation': f"Invoice {invoice_id} matched with rounding difference of ${diff:.2f} (Bank: ${bank_amount:.2f}, ERP: ${erp_amount:.2f})",
                    'amount_difference': diff,
                    'erp_data': erp_row.to_dict()
                }
        return None
    
    def fuzzy_match(self, bank_row: pd.Series, erp_df: pd.DataFrame, 
                   used_erp_ids: set) -> Optional[Dict[str, Any]]:
        bank_amount = float(bank_row['amount'])
        bank_date = bank_row.get('date')
        
        candidates = []
        
        for _, erp_row in erp_df.iterrows():
            erp_row_id = erp_row.get('erp_row_id')
            if erp_row_id in used_erp_ids:
                continue
            
            erp_amount = float(erp_row['amount'])
            amount_diff = abs(bank_amount - erp_amount)
            
            if amount_diff > config.FUZZY_AMOUNT_ABS:
                continue
            
            date_diff_days = 0
            if bank_date and erp_row.get('date'):
                try:
                    bank_dt = datetime.strptime(str(bank_date), "%Y-%m-%d")
                    erp_dt = datetime.strptime(str(erp_row['date']), "%Y-%m-%d")
                    date_diff_days = abs((bank_dt - erp_dt).days)
                except (ValueError, TypeError):
                    date_diff_days = 999
            
            if date_diff_days > config.FUZZY_DATE_DAYS:
                continue
            
            score = 1.0 - (amount_diff / config.FUZZY_AMOUNT_ABS) * 0.5
            score -= (date_diff_days / config.FUZZY_DATE_DAYS) * 0.3
            
            candidates.append({
                'erp_row': erp_row,
                'score': score,
                'amount_diff': amount_diff,
                'date_diff_days': date_diff_days
            })
        
        if candidates:
            best = max(candidates, key=lambda x: x['score'])
            if best['score'] >= config.CONFIDENCE_THRESHOLD_HUMAN_REVIEW:
                erp_row = best['erp_row']
                return {
                    'erp_row_id': erp_row.get('erp_row_id'),
                    'match_status': 'Probable Match',
                    'match_confidence': round(best['score'], 2),
                    'rule_fired': 'fuzzy_amount_date',
                    'explanation': f"Probable match based on amount difference ${best['amount_diff']:.2f} and date difference {best['date_diff_days']} days",
                    'amount_difference': best['amount_diff'],
                    'date_difference_days': best['date_diff_days'],
                    'erp_data': erp_row.to_dict()
                }
        
        return None
    
    def run(self, bank_df: pd.DataFrame, erp_df: pd.DataFrame, 
            llm_client=None) -> Dict[str, Any]:
        start_time = datetime.now()
        logger.info(f"[AGENT:{self.agent_name}] START run_id={self.run_id} inputs=bank_rows:{len(bank_df)}, erp_rows:{len(erp_df)}")
        
        try:
            results = []
            used_erp_ids = set()
            
            stats = {
                'exact_matches': 0,
                'rounding_matches': 0,
                'fuzzy_matches': 0,
                'no_match': 0
            }
            
            invoice_bank_df = bank_df[bank_df['is_non_invoice'] == False].copy() if 'is_non_invoice' in bank_df.columns else bank_df.copy()
            
            for idx, bank_row in invoice_bank_df.iterrows():
                match_result = None
                
                match_result = self.exact_match(bank_row, erp_df)
                if match_result:
                    stats['exact_matches'] += 1
                    used_erp_ids.add(match_result['erp_row_id'])
                else:
                    match_result = self.rounding_match(bank_row, erp_df)
                    if match_result:
                        stats['rounding_matches'] += 1
                        used_erp_ids.add(match_result['erp_row_id'])
                    else:
                        match_result = self.fuzzy_match(bank_row, erp_df, used_erp_ids)
                        if match_result:
                            stats['fuzzy_matches'] += 1
                            used_erp_ids.add(match_result['erp_row_id'])
                        else:
                            stats['no_match'] += 1
                            match_result = {
                                'erp_row_id': None,
                                'match_status': 'No Match',
                                'match_confidence': 0.0,
                                'rule_fired': 'no_match_found',
                                'explanation': 'No matching ERP record found',
                                'erp_data': {}
                            }
                
                result_row = {
                    'bank_ref': bank_row.get('ref_id'),
                    'bank_date': bank_row.get('date'),
                    'bank_invoice': bank_row.get('invoice_id'),
                    'bank_amount': bank_row.get('amount'),
                    'bank_description': bank_row.get('description'),
                    **match_result
                }
                results.append(result_row)
            
            matched_df = pd.DataFrame(results)
            
            llm_reasoning = self._generate_reasoning(bank_df, erp_df, stats, llm_client)
            
            result = {
                'success': True,
                'matched_data': matched_df,
                'used_erp_ids': used_erp_ids,
                'statistics': stats
            }
            
            log_entry = create_agent_log(
                run_id=self.run_id,
                agent_name=self.agent_name,
                input_summary=f"Bank rows: {len(bank_df)}, ERP rows: {len(erp_df)}",
                deterministic_output=stats,
                llm_reasoning=llm_reasoning,
                decision=f"Matching completed: {stats['exact_matches']} exact, {stats['rounding_matches']} rounding, {stats['fuzzy_matches']} fuzzy, {stats['no_match']} unmatched",
                confidence=0.95,
                rule_fired="multi_tier_matching"
            )
            save_agent_log(self.run_id, self.agent_name, log_entry)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"[AGENT:{self.agent_name}] END run_id={self.run_id} summary=Matched in {duration:.2f}s - exact:{stats['exact_matches']}, rounding:{stats['rounding_matches']}, fuzzy:{stats['fuzzy_matches']}, none:{stats['no_match']}")
            
            return result
            
        except Exception as e:
            logger.error(f"[AGENT:{self.agent_name}] ERROR run_id={self.run_id} error={str(e)}")
            return {
                'success': False,
                'error': str(e),
                'matched_data': pd.DataFrame(),
                'statistics': {}
            }
    
    def _generate_reasoning(self, bank_df: pd.DataFrame, erp_df: pd.DataFrame,
                           stats: Dict, llm_client=None) -> str:
        from app.core.llm_client import llm_client as llm
        
        total_processed = sum(stats.values())
        match_rate = ((stats['exact_matches'] + stats['rounding_matches'] + stats['fuzzy_matches']) / total_processed * 100) if total_processed > 0 else 0
        
        llm_analysis = ""
        if llm and llm.model:
            try:
                prompt = f"""Analyze this reconciliation matching result:
- Exact matches: {stats['exact_matches']}
- Rounding matches: {stats['rounding_matches']}
- Fuzzy matches: {stats['fuzzy_matches']}
- Unmatched: {stats['no_match']}
- Match rate: {match_rate:.1f}%

Provide:
1. Assessment of match quality
2. Potential issues to investigate
3. Confidence in the overall reconciliation

Respond in 3-4 sentences."""
                llm_analysis = llm.invoke(prompt, "You are a financial reconciliation expert.")
            except Exception as e:
                llm_analysis = f"[LLM analysis unavailable: {str(e)}]"
        
        reasoning = f"""Transaction Matching Analysis (AI-Powered):

1. Matching Results Summary:
   - Exact Matches: {stats['exact_matches']} (invoice ID + exact amount)
   - Rounding Matches: {stats['rounding_matches']} (invoice ID + amount within ${config.AMOUNT_ROUNDING_TOLERANCE})
   - Fuzzy Matches: {stats['fuzzy_matches']} (amount within ${config.FUZZY_AMOUNT_ABS}, date within {config.FUZZY_DATE_DAYS} days)
   - No Match Found: {stats['no_match']}

2. Overall Match Rate: {match_rate:.1f}%

3. Matching Logic Applied:
   - Tier 1 (Exact): Case-insensitive invoice ID match + exact amount equality
   - Tier 2 (Rounding): Invoice ID match + amount difference <= ${config.AMOUNT_ROUNDING_TOLERANCE}
   - Tier 3 (Fuzzy): Amount within ${config.FUZZY_AMOUNT_ABS} + date within {config.FUZZY_DATE_DAYS} days
   - Confidence threshold for fuzzy: {config.CONFIDENCE_THRESHOLD_HUMAN_REVIEW}

4. AI Analysis:
{llm_analysis if llm_analysis else 'LLM reasoning not available - configure GROQ_API_KEY for AI-powered analysis'}

5. Recommendations:
   - Review all 'No Match' items manually
   - Verify fuzzy matches with confidence < 0.8
   - Investigate rounding differences for pattern analysis
"""
        return reasoning
