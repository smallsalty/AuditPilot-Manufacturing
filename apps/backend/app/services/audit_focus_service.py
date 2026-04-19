from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai.llm_client import LLMClient, LLMRequestError
from app.repositories.enterprise_repository import EnterpriseRepository
from app.services.document_risk_service import DocumentRiskService


class AuditFocusService:
    SNAPSHOT_KEY = "audit_focus_snapshot"
    SNAPSHOT_VERSION = "audit-focus:v1"
    MAX_RISKS = 8

    SOURCE_LABELS = {
        "financial_anomaly": "来自财务异常",
        "risk_rule": "来自规则命中",
        "announcement_event": "来自公告事件",
        "penalty_event": "来自处罚/问询",
        "uploaded_document": "来自上传文档",
        "management_interview": "来自管理层访谈建议",
        "bank_statement": "来自银行流水/资金证据",
        "tax_analysis": "来自税务分析",
    }

    PRESET_OPERATIONS: dict[str, dict[str, list[str]]] = {
        "revenue_recognition": {
            "procedures": ["执行收入截止测试", "复核合同履约义务和收入确认时点", "检查期后回款", "访谈异常客户或销售负责人"],
            "evidence": ["主要销售合同", "出库单和验收单", "期后回款记录", "客户函证"],
            "accounts": ["主营业务收入", "应收账款", "合同负债"],
            "processes": ["收入确认", "销售发货", "客户回款"],
        },
        "receivable_recoverability": {
            "procedures": ["复核应收账款账龄", "实施函证和替代测试", "检查期后收款", "复核坏账准备计提依据"],
            "evidence": ["应收账款明细表", "账龄分析表", "函证回函", "期后收款凭证"],
            "accounts": ["应收账款", "坏账准备", "信用减值损失"],
            "processes": ["信用管理", "回款管理", "减值评估"],
        },
        "inventory_impairment": {
            "procedures": ["执行存货监盘", "分析库龄结构", "测试可变现净值", "复核跌价准备计提"],
            "evidence": ["存货明细表", "监盘记录", "库龄分析", "销售订单和市价资料"],
            "accounts": ["存货", "存货跌价准备", "营业成本"],
            "processes": ["存货管理", "成本核算", "减值测试"],
        },
        "cashflow_quality": {
            "procedures": ["复核现金流量表勾稽关系", "核对银行流水", "排查非经常性现金流", "分析经营现金流与利润背离原因"],
            "evidence": ["现金流量表工作底稿", "银行流水", "大额收付款凭证", "现金流分类明细"],
            "accounts": ["经营活动现金流量", "货币资金", "净利润"],
            "processes": ["资金收付", "现金流量表编制", "期末结账"],
        },
        "related_party_transaction": {
            "procedures": ["识别关联方完整性", "检查审批流程", "测试定价公允性", "追踪资金流水"],
            "evidence": ["关联方清单", "交易合同", "董事会或股东会决议", "银行流水"],
            "accounts": ["其他应收款", "关联交易", "应收应付款项"],
            "processes": ["关联方识别", "交易审批", "资金往来"],
        },
        "litigation_compliance": {
            "procedures": ["实施法律函证", "评估或有负债", "检查信息披露完整性", "跟踪整改进度"],
            "evidence": ["法律意见书", "法院或监管文书", "预计负债测算", "整改报告"],
            "accounts": ["预计负债", "营业外支出", "其他应付款"],
            "processes": ["合规管理", "或有事项评估", "信息披露"],
        },
        "internal_control_effectiveness": {
            "procedures": ["验证缺陷整改情况", "测试控制设计和执行有效性", "核查权限和审批链", "扩大关键控制样本"],
            "evidence": ["内控缺陷清单", "整改材料", "审批日志", "控制测试底稿"],
            "accounts": ["关键业务循环", "管理层凌驾控制", "信息系统权限"],
            "processes": ["内部控制", "权限审批", "缺陷整改"],
        },
        "audit_opinion_issue": {
            "procedures": ["复核审计意见涉及事项", "评价管理层整改计划", "检查期后事项", "判断对本期审计范围的影响"],
            "evidence": ["审计报告", "管理层说明", "整改计划", "期后事项资料"],
            "accounts": ["审计意见涉及科目", "重大错报风险", "期后事项"],
            "processes": ["财务报告", "整改跟踪", "审计沟通"],
        },
        "going_concern": {
            "procedures": ["复核管理层持续经营假设", "测试现金流预测", "检查债务到期安排", "评价期后融资和偿债计划"],
            "evidence": ["现金流预测", "借款合同", "授信文件", "期后融资资料"],
            "accounts": ["短期借款", "长期借款", "货币资金"],
            "processes": ["资金计划", "融资管理", "持续经营评估"],
        },
        "financing_pressure": {
            "procedures": ["分析债务到期结构", "检查授信额度", "核查担保质押安排", "执行偿债压力测试"],
            "evidence": ["债务台账", "授信合同", "担保和质押协议", "偿债计划"],
            "accounts": ["短期借款", "长期借款", "应付债券"],
            "processes": ["融资管理", "担保管理", "资金预算"],
        },
        "tax": {
            "procedures": ["核对纳税申报", "复核税会差异", "检查递延所得税确认", "执行税费支付截止测试"],
            "evidence": ["纳税申报表", "税会差异明细", "递延所得税测算", "税费支付凭证"],
            "accounts": ["所得税费用", "应交税费", "递延所得税资产"],
            "processes": ["税务申报", "所得税计提", "递延所得税复核"],
        },
        "announcement": {
            "procedures": ["核查公告正文事实", "识别责任主体和金额影响", "检查披露完整性", "跟踪后续整改和内控影响"],
            "evidence": ["公告原文", "董事会或监管文件", "整改进度材料", "相关会计处理资料"],
            "accounts": ["公告事项相关科目", "预计负债", "信息披露"],
            "processes": ["公告披露", "事项整改", "治理和内控"],
        },
        "default": {
            "procedures": ["复核风险形成原因", "获取关键支持性证据", "扩大相关样本测试", "与管理层访谈并形成审计结论"],
            "evidence": ["风险相关明细表", "管理层说明", "外部支持证据", "审计测试底稿"],
            "accounts": ["相关财务报表项目"],
            "processes": ["风险评估", "证据获取", "管理层沟通"],
        },
    }

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def build_focus(self, db: Session, enterprise_id: int) -> dict:
        from app.services.risk_analysis_service import RiskAnalysisService

        repo = EnterpriseRepository(db)
        enterprise = repo.get_by_id(enterprise_id)
        analysis_state = RiskAnalysisService().get_analysis_state(db, enterprise_id)
        risk_items = DocumentRiskService().list_risks(db, enterprise_id)
        selected_risks = risk_items[: self.MAX_RISKS]
        input_hash = self._input_hash(enterprise_id, selected_risks)

        cached = self._load_snapshot(enterprise, input_hash, analysis_state) if enterprise is not None else None
        if cached is not None:
            return cached

        generated_items = [
            self._build_focus_item(
                enterprise_name=getattr(enterprise, "name", "") or "",
                risk=item,
                index=index,
            )
            for index, item in enumerate(selected_risks, start=1)
        ]

        payload = self._build_payload(
            enterprise_id=enterprise_id,
            analysis_state=analysis_state,
            items=generated_items,
            cache_state="fallback" if all(item.get("cache_state") == "fallback" for item in generated_items) else "generated",
        )
        if enterprise is not None:
            self._store_snapshot(db, enterprise, input_hash, payload)
        return payload

    def _build_focus_item(self, *, enterprise_name: str, risk: dict[str, Any], index: int) -> dict[str, Any]:
        preset = self._preset_for_risk(risk)
        llm_result = self._generate_focus_with_llm(enterprise_name=enterprise_name, risk=risk, preset=preset)
        if llm_result is None:
            llm_result = self._fallback_focus(risk, preset)
            cache_state = "fallback"
        else:
            cache_state = "generated"

        procedures = self._dedupe(self._coerce_list(llm_result.get("procedures")) or preset["procedures"])[:5]
        evidence_to_obtain = self._dedupe(self._coerce_list(llm_result.get("evidence_to_obtain")) or preset["evidence"])[:5]
        focus_accounts = self._dedupe(self._coerce_list(llm_result.get("focus_accounts")) or preset["accounts"])[:6]
        focus_processes = self._dedupe(self._coerce_list(llm_result.get("focus_processes")) or preset["processes"])[:6]
        targeted_advice = str(llm_result.get("targeted_advice") or "").strip() or self._fallback_advice(risk, preset)
        rationale = str(llm_result.get("rationale") or "").strip()

        return {
            "id": f"focus-{index}",
            "title": risk["risk_name"],
            "summary": targeted_advice,
            "targeted_advice": targeted_advice,
            "sources": [self.SOURCE_LABELS.get(source, source) for source in (risk.get("evidence_types") or [])],
            "evidence_preview": [
                str(evidence.get("snippet") or evidence.get("content") or "")[:140]
                for evidence in (risk.get("evidence") or [])[:2]
            ],
            "expanded_sections": [
                {"title": "建议程序", "items": procedures},
                {"title": "需获取证据", "items": evidence_to_obtain},
                {"title": "生成依据", "items": [rationale] if rationale else [self._fallback_rationale(risk, preset)]},
            ],
            "focus_accounts": focus_accounts,
            "focus_processes": focus_processes,
            "recommended_procedures": procedures,
            "evidence_types": list(risk.get("evidence_types") or []),
            "rationale": rationale or self._fallback_rationale(risk, preset),
            "cache_state": cache_state,
        }

    def _generate_focus_with_llm(self, *, enterprise_name: str, risk: dict[str, Any], preset: dict[str, list[str]]) -> dict[str, Any] | None:
        if self.llm_client.config_error:
            return None
        risk_payload = {
            "risk_name": risk.get("risk_name"),
            "canonical_risk_key": risk.get("canonical_risk_key"),
            "risk_level": risk.get("risk_level"),
            "risk_score": risk.get("risk_score"),
            "summary": risk.get("summary"),
            "source_mode": risk.get("source_mode"),
            "evidence_types": risk.get("evidence_types") or [],
            "evidence": [
                {
                    "title": item.get("title"),
                    "snippet": item.get("snippet") or item.get("content"),
                    "source_label": item.get("source_label"),
                }
                for item in (risk.get("evidence") or [])[:3]
            ],
        }
        system_prompt = (
            "你是制造业上市公司审计项目经理。请基于风险证据生成针对性审计建议。"
            "只输出紧凑 JSON，不要 Markdown，不要解释。"
        )
        user_prompt = (
            f"企业：{enterprise_name or '当前企业'}\n"
            f"风险输入：{json.dumps(risk_payload, ensure_ascii=False)}\n"
            f"该风险类型的预设审计操作：{json.dumps(preset, ensure_ascii=False)}\n"
            "返回 JSON 对象，字段固定为 summary、targeted_advice、procedures、evidence_to_obtain、"
            "focus_accounts、focus_processes、rationale。summary 可等于 targeted_advice。"
            "targeted_advice 一句且不超过80字；rationale 一句且不超过80字；"
            "所有数组最多3条，单条不超过30字。不要复述风险标题。"
        )
        try:
            result = self.llm_client.chat_completion(
                system_prompt,
                user_prompt,
                json_mode=True,
                request_kind="audit_focus_recommendation",
                metadata={
                    "enterprise_id": risk.get("enterprise_id"),
                    "classified_type": "audit_focus",
                    "prompt_template": "audit_focus:targeted_recommendation:v1",
                    "schema_name": "audit_focus_recommendation_v1",
                    "context_variant": str(risk.get("canonical_risk_key") or "default"),
                },
                max_tokens=1600,
                max_attempts=2,
                strict_json_instruction=True,
            )
        except LLMRequestError:
            return None
        normalized = self._normalize_llm_result(result)
        if not normalized and isinstance(result, dict) and result.get("parsed_ok") is False and result.get("raw"):
            normalized = self._repair_llm_json(str(result.get("raw") or ""))
        advice = str(normalized.get("targeted_advice") or "").strip()
        return normalized if advice else None

    def _normalize_llm_result(self, result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            if result.get("parsed_ok") is False:
                return {}
            if isinstance(result.get("items"), list):
                item = next((entry for entry in result["items"] if isinstance(entry, dict)), None)
                if isinstance(item, dict):
                    return item
            return result
        if isinstance(result, list):
            item = next((entry for entry in result if isinstance(entry, dict)), None)
            if isinstance(item, dict):
                return item
        return {}

    def _repair_llm_json(self, raw_text: str) -> dict[str, Any]:
        text = str(raw_text or "").strip()
        if not text:
            return {}
        system_prompt = "你只负责修复 JSON 格式。不得新增事实，不得输出 Markdown。"
        user_prompt = (
            "把以下内容修复为一个合法紧凑 JSON 对象。字段仅保留 summary、targeted_advice、procedures、"
            "evidence_to_obtain、focus_accounts、focus_processes、rationale。"
            "如果原文末尾被截断，保留已完整出现的字段，并补齐必要括号和引号；数组最多3条。\n"
            f"原始内容：{text}"
        )
        try:
            repaired = self.llm_client.chat_completion(
                system_prompt,
                user_prompt,
                json_mode=True,
                request_kind="audit_focus_recommendation_repair",
                metadata={
                    "classified_type": "audit_focus",
                    "prompt_template": "audit_focus:json_repair:v1",
                    "schema_name": "audit_focus_recommendation_v1",
                    "context_variant": "json_repair",
                    "llm_input_chars": len(user_prompt),
                },
                max_tokens=900,
                max_attempts=1,
                strict_json_instruction=True,
            )
        except LLMRequestError:
            return {}
        return self._normalize_llm_result(repaired)

    def _fallback_focus(self, risk: dict[str, Any], preset: dict[str, list[str]]) -> dict[str, Any]:
        return {
            "summary": self._fallback_advice(risk, preset),
            "targeted_advice": self._fallback_advice(risk, preset),
            "procedures": preset["procedures"],
            "evidence_to_obtain": preset["evidence"],
            "focus_accounts": preset["accounts"],
            "focus_processes": preset["processes"],
            "rationale": self._fallback_rationale(risk, preset),
        }

    def _fallback_advice(self, risk: dict[str, Any], preset: dict[str, list[str]]) -> str:
        procedures = "、".join(preset["procedures"][:2])
        evidence = "、".join(preset["evidence"][:2])
        return f"针对{risk.get('risk_name') or '该风险'}，优先执行{procedures}，并取得{evidence}以判断其对财务报表和披露的影响。"

    def _fallback_rationale(self, risk: dict[str, Any], preset: dict[str, list[str]]) -> str:
        accounts = "、".join(preset["accounts"][:3])
        return f"该建议基于风险类型、现有证据和重点科目{accounts}生成，目标是把风险判断转化为可执行审计程序。"

    def _build_payload(
        self,
        *,
        enterprise_id: int,
        analysis_state: dict[str, Any],
        items: list[dict[str, Any]],
        cache_state: str,
    ) -> dict[str, Any]:
        focus_accounts: list[str] = []
        focus_processes: list[str] = []
        recommended_procedures: list[str] = []
        evidence_types: list[str] = []
        recommendation_items = []

        for item in items:
            focus_accounts = self._dedupe(focus_accounts + list(item.get("focus_accounts") or []))
            focus_processes = self._dedupe(focus_processes + list(item.get("focus_processes") or []))
            recommended_procedures = self._dedupe(recommended_procedures + list(item.get("recommended_procedures") or []))
            evidence_types = self._dedupe(evidence_types + list(item.get("evidence_types") or []))
            recommendation_items.append(
                {
                    "text": item.get("targeted_advice") or item.get("summary") or "",
                    "sources": list(item.get("sources") or []),
                    "rationale": item.get("rationale"),
                }
            )

        return {
            "enterprise_id": enterprise_id,
            "analysis_status": analysis_state["analysis_status"],
            "last_run_at": analysis_state["last_run_at"],
            "last_error": analysis_state["last_error"],
            "focus_accounts": focus_accounts,
            "focus_processes": focus_processes,
            "recommended_procedures": recommended_procedures,
            "evidence_types": evidence_types,
            "recommendations": [item["text"] for item in recommendation_items if item["text"]],
            "recommendation_items": recommendation_items,
            "items": items,
            "cache_state": cache_state,
        }

    def _input_hash(self, enterprise_id: int, risk_items: list[dict[str, Any]]) -> str:
        payload = {
            "enterprise_id": enterprise_id,
            "analysis_version": self.SNAPSHOT_VERSION,
            "risks": [
                {
                    "canonical_risk_key": item.get("canonical_risk_key"),
                    "risk_name": item.get("risk_name"),
                    "risk_level": item.get("risk_level"),
                    "risk_score": item.get("risk_score"),
                    "summary": item.get("summary"),
                    "source_mode": item.get("source_mode"),
                    "evidence_status": item.get("evidence_status"),
                    "evidence_types": item.get("evidence_types") or [],
                    "recommended_procedures": item.get("recommended_procedures") or [],
                    "evidence": [
                        {
                            "evidence_id": evidence.get("evidence_id"),
                            "title": evidence.get("title"),
                            "snippet": evidence.get("snippet") or evidence.get("content"),
                            "published_at": evidence.get("published_at"),
                        }
                        for evidence in (item.get("evidence") or [])[:3]
                    ],
                }
                for item in risk_items
            ],
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _load_snapshot(self, enterprise: Any, input_hash: str, analysis_state: dict[str, Any]) -> dict[str, Any] | None:
        portrait = enterprise.portrait if isinstance(getattr(enterprise, "portrait", None), dict) else {}
        snapshot = portrait.get(self.SNAPSHOT_KEY) if isinstance(portrait, dict) else None
        if not isinstance(snapshot, dict) or snapshot.get("input_hash") != input_hash:
            return None
        payload = dict(snapshot.get("payload") or {})
        payload["analysis_status"] = analysis_state["analysis_status"]
        payload["last_run_at"] = analysis_state["last_run_at"]
        payload["last_error"] = analysis_state["last_error"]
        payload["cache_state"] = "persisted_hit"
        return payload

    def _store_snapshot(self, db: Session, enterprise: Any, input_hash: str, payload: dict[str, Any]) -> None:
        snapshot = {
            "input_hash": input_hash,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": payload.get("items") or [],
            "recommendations": payload.get("recommendations") or [],
            "focus_accounts": payload.get("focus_accounts") or [],
            "focus_processes": payload.get("focus_processes") or [],
            "recommended_procedures": payload.get("recommended_procedures") or [],
            "evidence_types": payload.get("evidence_types") or [],
            "analysis_version": self.SNAPSHOT_VERSION,
            "payload": payload,
        }
        portrait = dict(enterprise.portrait or {})
        portrait[self.SNAPSHOT_KEY] = snapshot
        enterprise.portrait = portrait
        db.add(enterprise)
        db.commit()

    def _preset_for_risk(self, risk: dict[str, Any]) -> dict[str, list[str]]:
        key = str(risk.get("canonical_risk_key") or "").lower()
        name = str(risk.get("risk_name") or "").lower()
        combined = f"{key} {name}"
        if "tax_" in key or "税" in name:
            return self.PRESET_OPERATIONS["tax"]
        if "announcement_" in key or "公告" in name or "governance" in key:
            return self.PRESET_OPERATIONS["announcement"]
        for candidate in (
            "revenue_recognition",
            "receivable_recoverability",
            "inventory_impairment",
            "cashflow_quality",
            "related_party_transaction",
            "litigation_compliance",
            "internal_control_effectiveness",
            "audit_opinion_issue",
            "going_concern",
            "financing_pressure",
        ):
            if candidate in combined:
                return self.PRESET_OPERATIONS[candidate]
        return self.PRESET_OPERATIONS["default"]

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        items: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in items:
                items.append(text)
        return items

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            for sep in ("；", ";", "、", "\n"):
                if sep in text:
                    return [item.strip() for item in text.split(sep) if item.strip()]
            return [text]
        return []
