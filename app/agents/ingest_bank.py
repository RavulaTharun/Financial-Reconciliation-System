import re
import pandas as pd
import pdfplumber
from typing import Dict, Any, List
from datetime import datetime

from app.core.config import config
from app.core.utils import (
    get_agent_logger,
    normalize_amount,
    normalize_date,
    extract_invoice_id,
    create_agent_log,
    save_agent_log
)

logger = get_agent_logger("ingest_bank")

class BankIngestAgent:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.agent_name = "ingest_bank"
    
    def parse_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        logger.info(f"[AGENT:{self.agent_name}] START run_id={self.run_id} inputs=pdf_path:{pdf_path}")
        
        rows = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    continue
                
                lines = text.split('\n')
                for line in lines:
                    if 'Date' in line and 'Description' in line:
                        continue
                    if not line.strip():
                        continue
                    
                    parsed = self._parse_line(line)
                    if parsed:
                        parsed['source_page'] = page_num + 1
                        rows.append(parsed)
        
        logger.info(f"[AGENT:{self.agent_name}] Parsed {len(rows)} rows from PDF")
        return rows
    
    def _parse_line(self, line: str) -> Dict[str, Any] | None:
        date_pattern = r'(\d{4}-\d{2}-\d{2})'
        date_match = re.search(date_pattern, line)
        if not date_match:
            return None
        
        date_str = date_match.group(1)
        rest = line[date_match.end():].strip()
        
        amount_pattern = r'(-?[\d,]+\.?\d*)\s+(\d+)\s*$'
        amount_match = re.search(amount_pattern, rest)
        
        if not amount_match:
            return None
        
        amount = normalize_amount(amount_match.group(1))
        ref_id = amount_match.group(2)
        description = rest[:amount_match.start()].strip()
        
        invoice_id = extract_invoice_id(description)
        
        is_non_invoice = False
        non_invoice_type = None
        if invoice_id is None and amount < 0:
            is_non_invoice = True
            if 'adjustment' in description.lower():
                non_invoice_type = 'Adjustment'
            elif 'interest' in description.lower():
                non_invoice_type = 'Interest'
            elif 'bank fee' in description.lower():
                non_invoice_type = 'Bank Fee'
            else:
                non_invoice_type = 'Other'
        
        return {
            'date': normalize_date(date_str),
            'description': description,
            'invoice_id': invoice_id,
            'amount': amount,
            'ref_id': ref_id,
            'is_non_invoice': is_non_invoice,
            'non_invoice_type': non_invoice_type
        }
    
    def run(self, llm_client=None) -> Dict[str, Any]:
        start_time = datetime.now()
        
        try:
            rows = self.parse_pdf(config.BANK_PDF_PATH)
            
            df = pd.DataFrame(rows)
            
            invoice_rows = df[df['is_non_invoice'] == False].copy()
            non_invoice_rows = df[df['is_non_invoice'] == True].copy()
            
            output_path = f"{config.RESULTS_DIR}/bank_parsed.csv"
            df.to_csv(output_path, index=False)
            
            llm_reasoning = self._generate_reasoning(df, invoice_rows, non_invoice_rows, llm_client)
            
            result = {
                'success': True,
                'total_rows': len(df),
                'invoice_count': len(invoice_rows),
                'non_invoice_count': len(non_invoice_rows),
                'output_file': output_path,
                'sample_rows': df.head(10).to_dict('records'),
                'data': df
            }
            
            log_entry = create_agent_log(
                run_id=self.run_id,
                agent_name=self.agent_name,
                input_summary=f"PDF: {config.BANK_PDF_PATH}",
                deterministic_output={
                    'total_rows': len(df),
                    'invoice_count': len(invoice_rows),
                    'non_invoice_count': len(non_invoice_rows)
                },
                llm_reasoning=llm_reasoning,
                decision="Parsed bank statement PDF successfully",
                confidence=0.99,
                rule_fired="pdf_extraction"
            )
            save_agent_log(self.run_id, self.agent_name, log_entry)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"[AGENT:{self.agent_name}] END run_id={self.run_id} summary=Parsed {len(df)} rows in {duration:.2f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"[AGENT:{self.agent_name}] ERROR run_id={self.run_id} error={str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': pd.DataFrame()
            }
    
    def _generate_reasoning(self, df: pd.DataFrame, invoice_rows: pd.DataFrame, 
                           non_invoice_rows: pd.DataFrame, llm_client=None) -> str:
        reasoning = f"""Bank Statement Parsing Analysis:
        
1. Total Transactions Extracted: {len(df)}
2. Invoice Payments: {len(invoice_rows)} transactions with valid INV### format
3. Non-Invoice Items: {len(non_invoice_rows)} items (Adjustments, Interest, Bank Fees)

Normalization Applied:
- Dates converted to ISO format (YYYY-MM-DD)
- Amounts rounded to 2 decimal places
- Invoice IDs extracted using regex pattern INV\\d+

Notable Observations:
- Date range: {df['date'].min() if len(df) > 0 else 'N/A'} to {df['date'].max() if len(df) > 0 else 'N/A'}
- Total invoice amount: ${invoice_rows['amount'].sum():.2f if len(invoice_rows) > 0 else 0}
- Total non-invoice adjustments: ${non_invoice_rows['amount'].sum():.2f if len(non_invoice_rows) > 0 else 0}
"""
        return reasoning
