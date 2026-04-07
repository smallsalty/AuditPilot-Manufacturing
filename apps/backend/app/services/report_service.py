from sqlalchemy.orm import Session

from app.repositories.enterprise_repository import EnterpriseRepository
from app.services.audit_focus_service import AuditFocusService
from app.services.dashboard_service import DashboardService
from app.services.risk_analysis_service import RiskAnalysisService


class ReportService:
    def build_report(self, db: Session, enterprise_id: int, format_type: str = "json") -> dict:
        enterprise = EnterpriseRepository(db).get_by_id(enterprise_id)
        if enterprise is None:
            raise ValueError("企业不存在")
        dashboard = DashboardService().build_dashboard(db, enterprise_id)
        results = RiskAnalysisService().get_results(db, enterprise_id)
        focus = AuditFocusService().build_focus(db, enterprise_id)
        basis = [
            "财务指标增长率及周转率特征",
            "外部风险事件与治理结构信息",
            "文档抽取结果中的风险关键词段落",
            "规则引擎命中记录与异常检测结果",
        ]
        report = {
            "enterprise": dashboard["enterprise"],
            "overview": f"{enterprise.name} 属于 {enterprise.industry_tag}，系统已基于多源数据完成审计前期风险扫描。",
            "risk_profile": dashboard["score"],
            "top_risks": results[:5],
            "audit_focus": focus,
            "basis": basis,
        }
        if format_type == "markdown":
            markdown = [
                f"# {enterprise.name} 审计风险提示报告",
                "",
                "## 企业概况",
                report["overview"],
                "",
                "## 风险画像",
                f"- 综合评分：{dashboard['score']['total']}",
                f"- 财务风险：{dashboard['score']['financial']}",
                f"- 经营风险：{dashboard['score']['operational']}",
                f"- 合规风险：{dashboard['score']['compliance']}",
                "",
                "## Top 风险",
            ]
            for item in results[:5]:
                markdown.append(f"- {item['risk_name']}（{item['risk_level']}，{item['risk_score']}）")
            markdown.append("")
            markdown.append("## 审计重点")
            markdown.append(f"- 重点科目：{'、'.join(focus['focus_accounts'])}")
            markdown.append(f"- 重点流程：{'、'.join(focus['focus_processes'])}")
            markdown.append(f"- 建议程序：{'、'.join(focus['recommended_procedures'])}")
            report["markdown"] = "\n".join(markdown)
        return report

