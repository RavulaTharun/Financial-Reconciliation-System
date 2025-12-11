import pandas as pd
from typing import Dict, Any, List, Tuple
from datetime import datetime

from app.core.utils import (
    get_agent_logger,
    create_agent_log,
    save_agent_log
)

logger = get_agent_logger("dedupe")

class DedupeAgent:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.agent_name = "dedupe"
    
    def find_duplicates(self, df: pd.DataFrame, source: str, 
                       key_columns: List[str]) -> Tuple[pd.DataFrame, List[Dict]]:
        existing_cols = [col for col in key_columns if col in df.columns]
        
        if not existing_cols:
            return df, []
        
        df_copy = df.copy()
        df_copy['_dup_key'] = df_copy[existing_cols].astype(str).agg('|'.join, axis=1)
        
        duplicates = df_copy[df_copy.duplicated(subset='_dup_key', keep=False)]
        
        duplicate_groups = []
        for key, group in duplicates.groupby('_dup_key'):
            if len(group) > 1:
                duplicate_groups.append({
                    'key': key,
                    'count': len(group),
                    'indices': group.index.tolist(),
                    'source': source
                })
        
        df_copy = df_copy.drop(columns=['_dup_key'])
        
        return df_copy, duplicate_groups
    
    def run(self, bank_df: pd.DataFrame, erp_df: pd.DataFrame, 
            llm_client=None) -> Dict[str, Any]:
        start_time = datetime.now()
        logger.info(f"[AGENT:{self.agent_name}] START run_id={self.run_id} inputs=bank_rows:{len(bank_df)}, erp_rows:{len(erp_df)}")
        
        try:
            bank_processed, bank_duplicates = self.find_duplicates(
                bank_df, 
                source="Bank",
                key_columns=['invoice_id', 'amount', 'date']
            )
            
            erp_processed, erp_duplicates = self.find_duplicates(
                erp_df,
                source="ERP",
                key_columns=['invoice_id', 'amount', 'date']
            )
            
            bank_processed = self._mark_duplicates(bank_processed, bank_duplicates, "Duplicate in Bank")
            erp_processed = self._mark_duplicates(erp_processed, erp_duplicates, "Duplicate in ERP")
            
            llm_reasoning = self._generate_reasoning(
                bank_df, erp_df, bank_duplicates, erp_duplicates, llm_client
            )
            
            result = {
                'success': True,
                'bank_data': bank_processed,
                'erp_data': erp_processed,
                'bank_duplicates': bank_duplicates,
                'erp_duplicates': erp_duplicates,
                'bank_duplicate_count': sum(d['count'] - 1 for d in bank_duplicates),
                'erp_duplicate_count': sum(d['count'] - 1 for d in erp_duplicates)
            }
            
            log_entry = create_agent_log(
                run_id=self.run_id,
                agent_name=self.agent_name,
                input_summary=f"Bank rows: {len(bank_df)}, ERP rows: {len(erp_df)}",
                deterministic_output={
                    'bank_duplicate_groups': len(bank_duplicates),
                    'erp_duplicate_groups': len(erp_duplicates),
                    'bank_duplicate_rows': sum(d['count'] - 1 for d in bank_duplicates),
                    'erp_duplicate_rows': sum(d['count'] - 1 for d in erp_duplicates)
                },
                llm_reasoning=llm_reasoning,
                decision="Duplicate detection completed",
                confidence=0.99,
                rule_fired="exact_duplicate_match"
            )
            save_agent_log(self.run_id, self.agent_name, log_entry)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"[AGENT:{self.agent_name}] END run_id={self.run_id} summary=Found {len(bank_duplicates)} bank dup groups, {len(erp_duplicates)} erp dup groups in {duration:.2f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"[AGENT:{self.agent_name}] ERROR run_id={self.run_id} error={str(e)}")
            return {
                'success': False,
                'error': str(e),
                'bank_data': bank_df,
                'erp_data': erp_df
            }
    
    def _mark_duplicates(self, df: pd.DataFrame, duplicate_groups: List[Dict], 
                        label: str) -> pd.DataFrame:
        df_copy = df.copy()
        df_copy['duplicate_flag'] = False
        df_copy['duplicate_label'] = None
        
        for group in duplicate_groups:
            indices = group['indices']
            for idx in indices[1:]:
                if idx in df_copy.index:
                    df_copy.loc[idx, 'duplicate_flag'] = True
                    df_copy.loc[idx, 'duplicate_label'] = label
        
        return df_copy
    
    def _generate_reasoning(self, bank_df: pd.DataFrame, erp_df: pd.DataFrame,
                           bank_duplicates: List[Dict], erp_duplicates: List[Dict],
                           llm_client=None) -> str:
        bank_dup_details = []
        for dup in bank_duplicates[:5]:
            key_parts = dup['key'].split('|')
            bank_dup_details.append(f"  - {key_parts[0] if key_parts else 'Unknown'}: {dup['count']} occurrences")
        
        erp_dup_details = []
        for dup in erp_duplicates[:5]:
            key_parts = dup['key'].split('|')
            erp_dup_details.append(f"  - {key_parts[0] if key_parts else 'Unknown'}: {dup['count']} occurrences")
        
        reasoning = f"""Duplicate Detection Analysis:

1. Bank Statement Analysis:
   - Total records: {len(bank_df)}
   - Duplicate groups found: {len(bank_duplicates)}
   - Extra duplicate rows: {sum(d['count'] - 1 for d in bank_duplicates)}
   
   Top Bank Duplicates:
{chr(10).join(bank_dup_details) if bank_dup_details else '   None found'}

2. ERP Data Analysis:
   - Total records: {len(erp_df)}
   - Duplicate groups found: {len(erp_duplicates)}
   - Extra duplicate rows: {sum(d['count'] - 1 for d in erp_duplicates)}
   
   Top ERP Duplicates:
{chr(10).join(erp_dup_details) if erp_dup_details else '   None found'}

Detection Method:
- Duplicates identified by matching: invoice_id + amount + date
- First occurrence kept as primary, subsequent marked as duplicates
- Duplicates will be flagged in reconciliation output for review
"""
        return reasoning
