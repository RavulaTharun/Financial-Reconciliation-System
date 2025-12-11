import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime

from langchain_core.tools import tool

from app.core.config import config
from app.core.utils import (
    get_agent_logger,
    normalize_amount,
    normalize_date,
    extract_invoice_id,
    create_agent_log,
    save_agent_log
)

logger = get_agent_logger("ingest_erp")

@tool
def parse_excel_tool(excel_path: str) -> str:
    """Parse an ERP Excel file and extract transaction data."""
    return f"Parsing Excel at {excel_path}"

@tool
def detect_columns_tool(column_names: list) -> str:
    """Auto-detect invoice, amount, and date columns from column names."""
    return f"Detecting columns from: {column_names}"

class ERPIngestAgent:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.agent_name = "ingest_erp"
        self.invoice_synonyms = [
            'invoice', 'inv', 'invoice_id', 'invoiceid', 'invoice_no', 
            'invoice_number', 'inv_id', 'inv_no', 'invoice #', 'inv #',
            'reference', 'ref', 'transaction_id', 'txn_id'
        ]
        self.amount_synonyms = [
            'amount', 'amt', 'value', 'total', 'payment', 'sum',
            'invoice_amount', 'payment_amount', 'gross', 'net'
        ]
        self.date_synonyms = [
            'date', 'invoice_date', 'payment_date', 'transaction_date',
            'txn_date', 'posted_date', 'created_date', 'dt'
        ]
    
    def _find_column(self, columns: List[str], synonyms: List[str]) -> Optional[str]:
        columns_lower = {col.lower().strip(): col for col in columns}
        for synonym in synonyms:
            if synonym.lower() in columns_lower:
                return columns_lower[synonym.lower()]
        for synonym in synonyms:
            for col_lower, col_orig in columns_lower.items():
                if synonym.lower() in col_lower:
                    return col_orig
        return None
    
    def parse_excel(self, excel_path: str) -> pd.DataFrame:
        logger.info(f"[AGENT:{self.agent_name}] START run_id={self.run_id} inputs=excel_path:{excel_path}")
        
        df = pd.read_excel(excel_path)
        
        logger.info(f"[AGENT:{self.agent_name}] Discovered schema: {list(df.columns)}")
        
        return df
    
    def run(self, llm_client=None) -> Dict[str, Any]:
        start_time = datetime.now()
        
        try:
            df = self.parse_excel(config.ERP_EXCEL_PATH)
            
            invoice_col = self._find_column(df.columns, self.invoice_synonyms)
            amount_col = self._find_column(df.columns, self.amount_synonyms)
            date_col = self._find_column(df.columns, self.date_synonyms)
            
            column_mapping = {
                'invoice_column': invoice_col,
                'amount_column': amount_col,
                'date_column': date_col
            }
            
            warnings = []
            if not invoice_col:
                warnings.append("Could not detect invoice column - will attempt extraction from available columns")
            if not amount_col:
                warnings.append("Could not detect amount column")
            if not date_col:
                warnings.append("Could not detect date column")
            
            normalized_df = self._normalize_data(df, invoice_col, amount_col, date_col)
            
            output_path = f"{config.RESULTS_DIR}/erp_parsed.csv"
            normalized_df.to_csv(output_path, index=False)
            
            llm_reasoning = self._generate_reasoning(df, normalized_df, column_mapping, warnings, llm_client)
            
            result = {
                'success': True,
                'total_rows': len(normalized_df),
                'output_file': output_path,
                'schema': list(df.columns),
                'column_mapping': column_mapping,
                'warnings': warnings,
                'sample_rows': normalized_df.head(10).to_dict('records'),
                'data': normalized_df
            }
            
            log_entry = create_agent_log(
                run_id=self.run_id,
                agent_name=self.agent_name,
                input_summary=f"Excel: {config.ERP_EXCEL_PATH}, Schema: {list(df.columns)}",
                deterministic_output={
                    'total_rows': len(normalized_df),
                    'column_mapping': column_mapping
                },
                llm_reasoning=llm_reasoning,
                decision="Parsed ERP Excel successfully",
                confidence=0.95 if not warnings else 0.80,
                rule_fired="excel_extraction"
            )
            save_agent_log(self.run_id, self.agent_name, log_entry)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"[AGENT:{self.agent_name}] END run_id={self.run_id} summary=Parsed {len(normalized_df)} rows in {duration:.2f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"[AGENT:{self.agent_name}] ERROR run_id={self.run_id} error={str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': pd.DataFrame()
            }
    
    def _normalize_data(self, df: pd.DataFrame, invoice_col: Optional[str], 
                       amount_col: Optional[str], date_col: Optional[str]) -> pd.DataFrame:
        normalized = df.copy()
        normalized['erp_row_id'] = range(1, len(normalized) + 1)
        
        if invoice_col:
            normalized['invoice_id'] = normalized[invoice_col].apply(
                lambda x: extract_invoice_id(str(x)) if pd.notna(x) else None
            )
        else:
            for col in normalized.columns:
                sample = normalized[col].dropna().head(10).astype(str)
                if sample.str.contains(r'INV\d+', case=False, regex=True).any():
                    normalized['invoice_id'] = normalized[col].apply(
                        lambda x: extract_invoice_id(str(x)) if pd.notna(x) else None
                    )
                    break
            else:
                normalized['invoice_id'] = None
        
        if amount_col:
            normalized['amount'] = normalized[amount_col].apply(normalize_amount)
        else:
            normalized['amount'] = 0.0
        
        if date_col:
            normalized['date'] = normalized[date_col].apply(normalize_date)
        else:
            normalized['date'] = None
        
        return normalized
    
    def _generate_reasoning(self, original_df: pd.DataFrame, normalized_df: pd.DataFrame,
                           column_mapping: Dict, warnings: List[str], llm_client=None) -> str:
        reasoning = f"""ERP Data Parsing Analysis:

1. Total Records: {len(normalized_df)}
2. Original Schema: {list(original_df.columns)}

Column Detection Results:
- Invoice Column: {column_mapping['invoice_column'] or 'Not detected'}
- Amount Column: {column_mapping['amount_column'] or 'Not detected'}
- Date Column: {column_mapping['date_column'] or 'Not detected'}

Normalization Applied:
- Invoice IDs extracted using regex pattern INV\\d+
- Amounts rounded to 2 decimal places
- Dates converted to ISO format (YYYY-MM-DD)
- Added unique erp_row_id for tracking

Statistics:
- Valid invoice IDs: {normalized_df['invoice_id'].notna().sum()}
- Date range: {normalized_df['date'].min() if normalized_df['date'].notna().any() else 'N/A'} to {normalized_df['date'].max() if normalized_df['date'].notna().any() else 'N/A'}
- Total amount: ${normalized_df['amount'].sum():.2f}

Warnings: {warnings if warnings else 'None'}
"""
        return reasoning
