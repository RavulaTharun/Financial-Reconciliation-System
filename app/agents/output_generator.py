import os
import json
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List
from fpdf import FPDF

from app.core.config import config
from app.core.utils import get_agent_logger, create_agent_log, save_agent_log

logger = get_agent_logger("output_generator")

class OutputGenerator:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.output_dir = config.RESULTS_DIR
        os.makedirs(self.output_dir, exist_ok=True)
    
    def generate_reconciled_excel(self, explained_data: pd.DataFrame,
                                   classified_erp: pd.DataFrame,
                                   non_invoice_items: pd.DataFrame) -> str:
        output_path = f"{self.output_dir}/reconciled_master_{self.run_id}.xlsx"
        
        columns_to_keep = [
            'bank_ref', 'bank_date', 'bank_invoice', 'bank_amount',
            'erp_row_id', 'match_status', 'match_confidence',
            'exception_type', 'ai_explanation'
        ]
        
        export_df = explained_data.copy()
        
        if 'erp_data' in export_df.columns:
            erp_data_col = export_df['erp_data']
            export_df['erp_date'] = erp_data_col.apply(lambda x: x.get('date') if isinstance(x, dict) else None)
            export_df['erp_invoice'] = erp_data_col.apply(lambda x: x.get('invoice_id') if isinstance(x, dict) else None)
            export_df['erp_amount'] = erp_data_col.apply(lambda x: x.get('amount') if isinstance(x, dict) else None)
        
        final_columns = [
            'bank_ref', 'bank_date', 'bank_invoice', 'bank_amount',
            'erp_row_id', 'erp_date', 'erp_invoice', 'erp_amount',
            'match_status', 'match_confidence', 'exception_type', 
            'ai_explanation', 'rule_fired'
        ]
        
        for col in final_columns:
            if col not in export_df.columns:
                export_df[col] = None
        
        export_df = export_df[[c for c in final_columns if c in export_df.columns]]
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name='Reconciled Transactions', index=False)
            
            unmatched_erp = classified_erp[classified_erp['exception_type'] == 'Missing in Bank']
            if len(unmatched_erp) > 0:
                unmatched_erp.to_excel(writer, sheet_name='Missing in Bank', index=False)
            
            if len(non_invoice_items) > 0:
                non_invoice_items.to_excel(writer, sheet_name='Non-Invoice Items', index=False)
        
        logger.info(f"[OUTPUT] Generated reconciled Excel: {output_path}")
        return output_path
    
    def generate_summary_pdf(self, summary_report: str, match_stats: Dict,
                             exception_stats: Dict, bank_stats: Dict, 
                             erp_stats: Dict) -> str:
        output_path = f"{self.output_dir}/summary_report_{self.run_id}.pdf"
        
        pdf = FPDF()
        pdf.add_page()
        
        pdf.set_font('Helvetica', 'B', 16)
        pdf.cell(0, 10, 'Financial Reconciliation Report', ln=True, align='C')
        pdf.ln(5)
        
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 6, f'Run ID: {self.run_id}', ln=True)
        pdf.cell(0, 6, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', ln=True)
        pdf.ln(5)
        
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(0, 8, 'Executive Summary', ln=True)
        pdf.set_font('Helvetica', '', 10)
        
        total_bank = bank_stats.get('total_rows', 0)
        total_matched = match_stats.get('exact_matches', 0) + match_stats.get('rounding_matches', 0) + match_stats.get('fuzzy_matches', 0)
        match_rate = (total_matched / bank_stats.get('invoice_count', 1) * 100) if bank_stats.get('invoice_count', 0) > 0 else 0
        
        pdf.cell(0, 6, f'Bank Transactions: {total_bank}', ln=True)
        pdf.cell(0, 6, f'ERP Records: {erp_stats.get("total_rows", 0)}', ln=True)
        pdf.cell(0, 6, f'Overall Match Rate: {match_rate:.1f}%', ln=True)
        pdf.ln(5)
        
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(0, 8, 'Matching Results', ln=True)
        pdf.set_font('Helvetica', '', 10)
        
        pdf.cell(0, 6, f'Exact Matches: {match_stats.get("exact_matches", 0)}', ln=True)
        pdf.cell(0, 6, f'Rounding Matches: {match_stats.get("rounding_matches", 0)}', ln=True)
        pdf.cell(0, 6, f'Fuzzy Matches: {match_stats.get("fuzzy_matches", 0)}', ln=True)
        pdf.cell(0, 6, f'Unmatched: {match_stats.get("no_match", 0)}', ln=True)
        pdf.ln(5)
        
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(0, 8, 'Exceptions Identified', ln=True)
        pdf.set_font('Helvetica', '', 10)
        
        pdf.cell(0, 6, f'Missing in ERP: {exception_stats.get("missing_in_erp", 0)}', ln=True)
        pdf.cell(0, 6, f'Missing in Bank: {exception_stats.get("missing_in_bank", 0)}', ln=True)
        pdf.cell(0, 6, f'Non-Invoice Items: {exception_stats.get("non_invoice_items", 0)}', ln=True)
        pdf.cell(0, 6, f'Manual Review Required: {exception_stats.get("manual_review", 0)}', ln=True)
        pdf.ln(5)
        
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(0, 8, 'AI Agent Workflow', ln=True)
        pdf.set_font('Helvetica', '', 10)
        
        agents = [
            '1. BankIngestAgent - Parsed bank statement PDF',
            '2. ERPIngestAgent - Parsed ERP Excel data',
            '3. DedupeAgent - Detected duplicate transactions',
            '4. MatcherAgent - Performed multi-tier matching',
            '5. ClassifierAgent - Classified exceptions',
            '6. ExplainAgent - Generated explanations'
        ]
        for agent in agents:
            pdf.cell(0, 6, agent, ln=True)
        
        pdf.ln(5)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(0, 8, 'Recommendations', ln=True)
        pdf.set_font('Helvetica', '', 10)
        
        recommendations = [
            '- Review all Missing in ERP items for data entry gaps',
            '- Verify Missing in Bank items for timing differences',
            '- Manually verify low-confidence fuzzy matches',
            '- Non-invoice items should be reconciled separately'
        ]
        for rec in recommendations:
            pdf.cell(0, 6, rec, ln=True)
        
        pdf.output(output_path)
        logger.info(f"[OUTPUT] Generated summary PDF: {output_path}")
        return output_path
    
    def generate_config_snapshot(self) -> str:
        output_path = f"{self.output_dir}/{self.run_id}_config.json"
        
        config_data = {
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "thresholds": {
                "amount_rounding_tolerance": config.AMOUNT_ROUNDING_TOLERANCE,
                "fuzzy_amount_abs": config.FUZZY_AMOUNT_ABS,
                "fuzzy_date_days": config.FUZZY_DATE_DAYS,
                "confidence_threshold_human_review": config.CONFIDENCE_THRESHOLD_HUMAN_REVIEW
            },
            "model": config.LLM_MODEL,
            "vector_db": config.VECTOR_DB
        }
        
        with open(output_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        logger.info(f"[OUTPUT] Generated config snapshot: {output_path}")
        return output_path
    
    def generate_workflow_graph(self) -> str:
        output_path = f"{self.output_dir}/workflow_graph_{self.run_id}.txt"
        
        graph_text = """
RECONCILIATION WORKFLOW GRAPH
=============================

    +------------------+
    |   ingest_bank    |
    +------------------+
            |
            v
    +------------------+
    |   ingest_erp     |
    +------------------+
            |
            v
    +------------------+
    |     dedupe       |
    +------------------+
            |
            v
    +------------------+
    |     matcher      |
    | (exact/rounding/ |
    |     fuzzy)       |
    +------------------+
            |
            v
    +------------------+
    |   classifier     |
    +------------------+
            |
            v
    +------------------+
    |     explain      |
    +------------------+
            |
            v
    +------------------+
    |     output       |
    +------------------+
            |
            v
         [END]

Legend:
- Each node represents an AI agent
- Agents execute sequentially (LangGraph orchestrated)
- All agent decisions are logged for audit
"""
        
        with open(output_path, 'w') as f:
            f.write(graph_text)
        
        logger.info(f"[OUTPUT] Generated workflow graph: {output_path}")
        return output_path
    
    def generate_all_outputs(self, explained_data: pd.DataFrame,
                             summary_report: str,
                             classified_erp: pd.DataFrame,
                             non_invoice_items: pd.DataFrame,
                             match_stats: Dict,
                             exception_stats: Dict,
                             bank_stats: Dict,
                             erp_stats: Dict) -> Dict[str, Any]:
        
        logger.info(f"[OUTPUT] Generating all output files for run_id={self.run_id}")
        
        output_files = []
        
        excel_path = self.generate_reconciled_excel(
            explained_data, classified_erp, non_invoice_items
        )
        output_files.append(excel_path)
        
        pdf_path = self.generate_summary_pdf(
            summary_report, match_stats, exception_stats, bank_stats, erp_stats
        )
        output_files.append(pdf_path)
        
        config_path = self.generate_config_snapshot()
        output_files.append(config_path)
        
        graph_path = self.generate_workflow_graph()
        output_files.append(graph_path)
        
        log_entry = create_agent_log(
            run_id=self.run_id,
            agent_name="output_generator",
            input_summary="Generate all reconciliation outputs",
            deterministic_output={"output_files": output_files},
            llm_reasoning="Generated all required output files including Excel, PDF, config, and workflow graph",
            decision="Output generation complete",
            confidence=1.0,
            rule_fired="output_generation"
        )
        save_agent_log(self.run_id, "output_generator", log_entry)
        
        return {
            "success": True,
            "output_files": output_files
        }
