from __future__ import annotations

from app.ai.document_prompt_registry import DocumentPromptRegistry
from app.models import DocumentMeta
from app.services.document_classify_service import DocumentClassifyService
from app.services.financial_analysis_service import FinancialAnalysisService


def test_quarter_report_sync_type_stays_quarter_report():
    document = DocumentMeta(
        id=1,
        enterprise_id=100,
        document_name="2025年第一季度报告",
        document_type="quarter_report",
    )

    result = DocumentClassifyService().classify(document, "普通正文")

    assert result.classified_type == "quarter_report"


def test_financial_analysis_supports_quarter_report_not_annual_summary():
    assert "quarter_report" in FinancialAnalysisService.SUPPORTED_DOCUMENT_TYPES
    assert "annual_summary" not in FinancialAnalysisService.SUPPORTED_DOCUMENT_TYPES
    assert DocumentPromptRegistry.resolve_prompt_type("quarter_report") == "annual_report"
    assert FinancialAnalysisService.SNAPSHOT_VERSION == "financial-analysis-snapshot:v2"
