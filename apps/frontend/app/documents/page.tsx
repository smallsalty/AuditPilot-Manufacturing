"use client";

import { useEffect, useMemo, useState } from "react";
import type { DocumentExtractItem, DocumentListItem } from "@auditpilot/shared-types";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import {
  formatAnalysisGroup,
  formatAnalysisMode,
  formatAnalysisStatus,
  formatCacheState,
  formatCanonicalRiskKey,
  formatDocumentType,
  formatEventType,
  formatKnownLabel,
  formatParseStatus,
  formatRuleCode,
  formatSourceName,
} from "@/lib/display-labels";
import { useDocumentsResource, useFinancialAnalysisResource, useReadinessResource } from "@/lib/enterprise-resources";

const CLASSIFICATION_OPTIONS = [
  "annual_report",
  "annual_summary",
  "audit_report",
  "internal_control_report",
  "announcement_event",
  "general",
];

const EVENT_OPTIONS = [
  "share_repurchase",
  "convertible_bond",
  "executive_change",
  "litigation",
  "penalty_or_inquiry",
  "guarantee",
  "related_party_transaction",
  "audit_opinion_issue",
  "internal_control_issue",
];

const EMPTY_REASON_LABELS: Record<string, string> = {
  no_sync_run: "该企业还没有执行过官方同步，请先手动同步或上传文档。",
  generic_window_no_documents: "当前同步窗口内没有命中官方文档，建议手动刷新或重新同步。",
  annual_package_not_published: "最近一套年报包尚未披露，或当前检索窗口内尚未命中。",
  provider_returned_only_other: "当前窗口只抓到非文档公告，尚未抓到年报、审计报告或内控报告。",
  provider_error: "官方同步过程中出现上游错误，本次未产出文档。",
};

type PageAction =
  | { kind: "idle" }
  | { kind: "reading"; message: string }
  | { kind: "analyzing"; message: string };

function renderStructuredFields(extract: DocumentExtractItem) {
  const rows: string[] = [];
  if (extract.metric_name) {
    rows.push(`数值：${extract.metric_name} ${extract.metric_value ?? "-"} ${extract.metric_unit ?? ""}`.trim());
  }
  if (extract.event_type) {
    rows.push(`事件：${formatEventType(extract.event_type)}`);
  }
  if (extract.amount != null) {
    rows.push(`金额：${extract.amount}`);
  }
  if (extract.counterparty) {
    rows.push(`对手方：${extract.counterparty}`);
  }
  if (extract.opinion_type) {
    rows.push(`意见：${extract.opinion_type}`);
  }
  if (extract.conclusion) {
    rows.push(`结论：${extract.conclusion}`);
  }
  return rows;
}

function formatTimestamp(value?: string | null): string {
  if (!value) {
    return "暂无";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

export default function DocumentsPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError, invalidateEnterpriseResources } = useEnterpriseContext();
  const {
    data: readiness,
    loading: readinessLoading,
    error: readinessError,
    refresh: refreshReadiness,
  } = useReadinessResource(currentEnterpriseId);
  const { data: documents, loading: documentsLoading, error: documentsError, refresh: refreshDocuments } =
    useDocumentsResource(currentEnterpriseId);
  const {
    data: financialAnalysis,
    loading: financialAnalysisLoading,
    error: financialAnalysisError,
    refresh: refreshFinancialAnalysis,
  } = useFinancialAnalysisResource(currentEnterpriseId);

  const [file, setFile] = useState<File | null>(null);
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);
  const [extracts, setExtracts] = useState<DocumentExtractItem[]>([]);
  const [message, setMessage] = useState("支持 PDF 或文本文件。文档需手动解析，解析结果会显示规则命中、结构化字段和财报专项结果。");
  const [syncGapRetryCount, setSyncGapRetryCount] = useState(0);
  const [pageAction, setPageAction] = useState<PageAction>({ kind: "idle" });

  useEffect(() => {
    setActiveDocumentId(null);
    setExtracts([]);
    setFile(null);
    setSyncGapRetryCount(0);
    setPageAction({ kind: "idle" });
  }, [currentEnterpriseId]);

  useEffect(() => {
    if (
      !currentEnterpriseId ||
      documentsLoading ||
      readinessLoading ||
      documentsError ||
      readinessError ||
      (documents?.length ?? 0) > 0 ||
      (readiness?.official_doc_count ?? 0) === 0 ||
      syncGapRetryCount > 0
    ) {
      return;
    }

    const timer = window.setTimeout(() => {
      setSyncGapRetryCount(1);
      setPageAction({ kind: "reading", message: "官方文档已同步，正在刷新列表..." });
      void Promise.allSettled([refreshReadiness(), refreshDocuments(), refreshFinancialAnalysis()]).finally(() => {
        setPageAction((current) => (current.kind === "reading" ? { kind: "idle" } : current));
      });
    }, 1500);

    return () => window.clearTimeout(timer);
  }, [
    currentEnterpriseId,
    documents,
    documentsError,
    documentsLoading,
    readiness,
    readinessError,
    readinessLoading,
    refreshDocuments,
    refreshFinancialAnalysis,
    refreshReadiness,
    syncGapRetryCount,
  ]);

  const activeDocument = useMemo(
    () => documents?.find((item) => item.id === activeDocumentId) ?? null,
    [activeDocumentId, documents],
  );

  const hasSyncGap = Boolean(
    currentEnterpriseId &&
      !documentsLoading &&
      !readinessLoading &&
      !documentsError &&
      !readinessError &&
      (documents?.length ?? 0) === 0 &&
      (readiness?.official_doc_count ?? 0) > 0,
  );
  const readinessEmptyMessage =
    readiness?.empty_reason && EMPTY_REASON_LABELS[readiness.empty_reason]
      ? EMPTY_REASON_LABELS[readiness.empty_reason]
      : "当前企业暂无文档。可先同步官方公告或上传 PDF。";

  const refreshAll = async () => {
    setPageAction({ kind: "reading", message: "正在读取当前企业的文档与财报专项结果..." });
    await Promise.allSettled([refreshReadiness({ force: true }), refreshDocuments({ force: true }), refreshFinancialAnalysis({ force: true })]);
    setPageAction({ kind: "idle" });
  };

  const loadExtracts = async (document: DocumentListItem, mode: PageAction["kind"] = "reading") => {
    const readingMessage = mode === "analyzing" ? "正在刷新抽取结果..." : "正在读取文档抽取结果...";
    setPageAction({ kind: mode, message: readingMessage });
    try {
      const response = await api.getDocumentExtracts(document.id);
      setActiveDocumentId(document.id);
      setExtracts(response.extracts);
      setMessage(`已加载 ${document.document_name} 的抽取结果。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "抽取结果加载失败。");
    } finally {
      setPageAction({ kind: "idle" });
    }
  };

  const upload = async () => {
    if (!file || !currentEnterpriseId) {
      return;
    }
    setPageAction({ kind: "analyzing", message: "正在上传文档..." });
    try {
      const result = await api.uploadDocument(currentEnterpriseId, file);
      invalidateEnterpriseResources(currentEnterpriseId, ["documents", "readiness", "financialAnalysis"]);
      await refreshAll();
      setMessage(`文档 ${result.document_name} 上传成功，待手动解析。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "文档上传失败。");
    } finally {
      setPageAction({ kind: "idle" });
    }
  };

  const parse = async (document: DocumentListItem) => {
    setPageAction({ kind: "analyzing", message: "正在解析文档并刷新结构化结果..." });
    try {
      await api.parseDocument(document.id);
      const response = await api.getDocumentExtracts(document.id);
      invalidateEnterpriseResources(currentEnterpriseId ?? 0, ["documents", "readiness", "financialAnalysis"]);
      await Promise.allSettled([refreshReadiness({ force: true }), refreshDocuments({ force: true }), refreshFinancialAnalysis({ force: true })]);
      setActiveDocumentId(document.id);
      setExtracts(response.extracts);
      setMessage(`已生成 ${response.extracts.length} 条结构化抽取结果。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "文档解析失败。");
    } finally {
      setPageAction({ kind: "idle" });
    }
  };

  const updateClassification = async (document: DocumentListItem, classifiedType: string) => {
    setPageAction({ kind: "analyzing", message: "正在重算文档分类并刷新分析结果..." });
    try {
      await api.overrideDocumentClassification(document.id, classifiedType);
      invalidateEnterpriseResources(currentEnterpriseId ?? 0, ["documents", "financialAnalysis", "readiness"]);
      await Promise.allSettled([refreshDocuments({ force: true }), refreshFinancialAnalysis({ force: true }), refreshReadiness({ force: true })]);
      if (activeDocumentId === document.id) {
        await loadExtracts(document, "analyzing");
      }
      setMessage(`已将文档分类修正为 ${formatDocumentType(classifiedType)}。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "文档分类修正失败。");
      setPageAction({ kind: "idle" });
    }
  };

  const updateEventType = async (extract: DocumentExtractItem, eventType: string) => {
    if (!activeDocumentId || !extract.evidence_span_id) {
      return;
    }
    setPageAction({ kind: "analyzing", message: "正在更新事件类型并刷新抽取结果..." });
    try {
      await api.overrideExtractEventType(activeDocumentId, extract.evidence_span_id, eventType);
      const response = await api.getDocumentExtracts(activeDocumentId);
      setExtracts(response.extracts);
      setMessage(`已将事件类型修正为 ${formatEventType(eventType)}。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "事件类型修正失败。");
    } finally {
      setPageAction({ kind: "idle" });
    }
  };

  const topStatus = useMemo(() => {
    if (pageAction.kind === "analyzing") {
      return { label: "分析中", message: pageAction.message, tone: "border-amber-300/30 bg-amber-300/10 text-amber-100" };
    }
    if (pageAction.kind === "reading" || documentsLoading || readinessLoading || financialAnalysisLoading) {
      return {
        label: "读取中",
        message: pageAction.kind === "reading" ? pageAction.message : "正在读取当前企业的文档、就绪状态和财报专项结果...",
        tone: "border-sky-300/30 bg-sky-300/10 text-sky-100",
      };
    }
    if (readiness?.manual_parse_required) {
      const count = readiness.documents_pending_parse ?? 0;
      return {
        label: "已同步，待手动解析",
        message: count > 0 ? `已同步 ${count} 份待解析文档，请手动点击“解析”或“查看抽取”。` : "官方文档已同步，待手动解析。",
        tone: "border-emerald-300/30 bg-emerald-300/10 text-emerald-100",
      };
    }
    if (hasSyncGap) {
      return {
        label: "同步/刷新中",
        message: syncGapRetryCount === 0 ? "官方文档已存在，列表正在同步刷新..." : "同步仍在收尾，请手动刷新。",
        tone: "border-white/20 bg-white/10 text-haze/80",
      };
    }
    return {
      label: "空闲",
      message,
      tone: "border-white/10 bg-white/5 text-haze/75",
    };
  }, [
    documentsLoading,
    financialAnalysisLoading,
    hasSyncGap,
    message,
    pageAction,
    readiness?.documents_pending_parse,
    readiness?.manual_parse_required,
    readinessLoading,
    syncGapRetryCount,
  ]);

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">文档中心</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">
              {currentEnterprise ? `${currentEnterprise.name} 文档中心` : "文档中心"}
            </h2>
            <p className="mt-2 text-haze/75">{message}</p>
            {currentEnterprise ? (
              <p className="mt-3 text-sm text-haze/65">
                企业 ID：{currentEnterpriseId} | 官方文档 {readiness?.official_doc_count ?? 0} 份
              </p>
            ) : null}
          </div>
          <div className="flex flex-col gap-3 lg:flex-row">
            <input
              type="file"
              accept=".pdf,.txt"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-haze/75"
            />
            <Button variant="outline" onClick={() => void refreshAll()} disabled={pageAction.kind !== "idle"}>
              刷新文档
            </Button>
            <Button onClick={() => void upload()} disabled={!file || !currentEnterpriseId || pageAction.kind !== "idle"}>
              上传文档
            </Button>
          </div>
        </div>
      </Card>

      <Card>
        <div className={`rounded-2xl border px-4 py-4 text-sm ${topStatus.tone}`}>
          <p className="text-xs uppercase tracking-[0.2em]">{topStatus.label}</p>
          <p className="mt-2">{topStatus.message}</p>
        </div>
      </Card>

      {enterpriseError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">{enterpriseError}</div>
        </Card>
      ) : !currentEnterpriseId ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">请先选择企业。</div>
        </Card>
      ) : documentsError || readinessError || financialAnalysisError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
            {documentsError ?? readinessError ?? financialAnalysisError}
          </div>
        </Card>
      ) : (
        <>
          <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">文档列表</p>
              {documents && documents.length > 0 ? (
                <div className="mt-4 space-y-3">
                  {documents.map((document) => (
                    <div key={document.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <div className="flex flex-col gap-3">
                        <div>
                          <p className="font-medium text-white">{document.document_name}</p>
                          <p className="mt-1 text-xs uppercase tracking-[0.2em] text-steel">
                            {formatDocumentType(document.classified_type ?? document.document_type)} |{" "}
                            {formatParseStatus(document.parse_status)} | {formatSourceName(document.source)}
                          </p>
                          <p className="mt-2 text-xs text-haze/65">
                            分析状态：{formatAnalysisStatus(document.analysis_status)} | {formatAnalysisMode(document.analysis_mode)}
                          </p>
                          {document.analysis_groups?.length ? (
                            <p className="mt-2 text-xs text-haze/65">
                              分析分组：{document.analysis_groups.map((item) => formatAnalysisGroup(item)).join(" / ")}
                            </p>
                          ) : null}
                          {document.last_error_message ? (
                            <p className="mt-2 text-xs text-amber-200">
                              最近错误：{document.last_error_message}
                              {document.last_error_at ? ` | ${formatTimestamp(document.last_error_at)}` : ""}
                            </p>
                          ) : null}
                        </div>
                        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
                          <select
                            className="rounded-2xl border border-white/10 bg-black/10 px-3 py-2 text-sm text-haze/80"
                            value={document.classified_type ?? document.document_type}
                            onChange={(event) => void updateClassification(document, event.target.value)}
                            disabled={pageAction.kind !== "idle"}
                          >
                            {CLASSIFICATION_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {formatDocumentType(option)}
                              </option>
                            ))}
                          </select>
                          <Button variant="outline" onClick={() => void loadExtracts(document)} disabled={pageAction.kind !== "idle"}>
                            查看抽取
                          </Button>
                          <Button
                            onClick={() => void parse(document)}
                            disabled={pageAction.kind !== "idle" || document.parse_status === "parsing"}
                          >
                            {document.parse_status === "parsed" ? "重新解析" : "解析"}
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                  <p>{readinessEmptyMessage}</p>
                  {readiness?.manual_parse_required ? (
                    <p className="mt-2 text-xs text-haze/60">
                      已同步 {readiness.documents_pending_parse} 份官方文档，待手动解析。
                    </p>
                  ) : null}
                  {readiness?.last_sync_diagnostics?.initial_window ? (
                    <p className="mt-2 text-xs text-haze/60">
                      最近同步窗口：{readiness.last_sync_diagnostics.initial_window.date_from} ~{" "}
                      {readiness.last_sync_diagnostics.initial_window.date_to}
                    </p>
                  ) : null}
                </div>
              )}
            </Card>

            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">抽取明细</p>
              {activeDocument ? <p className="mt-2 text-sm text-haze/70">当前文档：{activeDocument.document_name}</p> : null}
              {extracts.length > 0 ? (
                <div className="mt-4 space-y-3">
                  {extracts.map((extract, index) => {
                    const structuredRows = renderStructuredFields(extract);
                    return (
                      <details key={extract.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                        <summary className="list-none cursor-pointer">
                          <div className="flex items-start gap-3">
                            <span className="pt-0.5 text-sm font-semibold text-amber-300">{index + 1}.</span>
                            <div className="min-w-0 flex-1">
                              <p className="font-medium text-white">{formatKnownLabel(extract.title)}</p>
                              <p className="mt-2 text-sm text-haze/80">{extract.problem_summary}</p>
                            </div>
                          </div>
                        </summary>
                        <div className="mt-4 space-y-4 border-t border-white/10 pt-4">
                          <section>
                            <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">规则与风险键</p>
                            <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-haze/80">
                              {extract.applied_rules.length ? (
                                <p>规则：{extract.applied_rules.map((item) => formatRuleCode(item)).join(" / ")}</p>
                              ) : (
                                <p>规则：未命中</p>
                              )}
                              {extract.canonical_risk_key ? (
                                <p className="mt-2">风险键：{formatCanonicalRiskKey(extract.canonical_risk_key)}</p>
                              ) : null}
                            </div>
                          </section>
                          <section>
                            <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">证据摘要</p>
                            <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-haze/80">
                              {extract.evidence_excerpt}
                            </div>
                          </section>
                          {structuredRows.length ? (
                            <section>
                              <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">结构化字段</p>
                              <div className="space-y-2 text-sm text-haze/80">
                                {structuredRows.map((row) => (
                                  <p key={row}>{row}</p>
                                ))}
                              </div>
                            </section>
                          ) : null}
                          {extract.evidence_span_id ? (
                            <section>
                              <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">事件修正</p>
                              <select
                                className="rounded-2xl border border-white/10 bg-black/10 px-3 py-2 text-sm text-haze/80"
                                value={extract.event_type ?? ""}
                                onChange={(event) => void updateEventType(extract, event.target.value)}
                                disabled={pageAction.kind !== "idle"}
                              >
                                <option value="">请选择事件类型</option>
                                {EVENT_OPTIONS.map((option) => (
                                  <option key={option} value={option}>
                                    {formatEventType(option)}
                                  </option>
                                ))}
                              </select>
                            </section>
                          ) : null}
                        </div>
                      </details>
                    );
                  })}
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                  当前未读取任何文档抽取结果。点击“查看抽取”后才会读取，不会自动展开。
                </div>
              )}
            </Card>
          </div>

          <Card>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">财报专项分析</p>
            <p className="mt-2 text-sm text-haze/75">{financialAnalysis?.summary ?? "当前尚未生成财报专项聚合结果。"}</p>
            {financialAnalysis ? (
              <div className="mt-3 flex flex-wrap gap-3 text-xs text-haze/65">
                <span>最近更新时间：{formatTimestamp(financialAnalysis.updated_at)}</span>
                <span>摘要来源：{financialAnalysis.summary_mode === "llm" ? "MiniMax" : "降级摘要"}</span>
                <span>返回来源：{formatCacheState(financialAnalysis.cache_state)}</span>
              </div>
            ) : null}
            {financialAnalysis?.anomalies?.length ? (
              <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_0.9fr]">
                <div className="space-y-3">
                  {financialAnalysis.anomalies.slice(0, 6).map((item) => (
                    <div key={`${item.document_id}-${item.title}`} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="font-medium text-white">{formatKnownLabel(item.title)}</p>
                      <p className="mt-2 text-sm text-haze/80">{item.summary}</p>
                      <p className="mt-2 text-xs text-haze/65">
                        {item.document_name}
                        {item.period ? ` | ${item.period}` : ""}
                        {item.metric_name ? ` | ${item.metric_name}` : ""}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="space-y-4">
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-steel">重点科目</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {financialAnalysis.focus_accounts.map((item) => (
                        <span key={item} className="rounded-full bg-black/10 px-3 py-1 text-xs text-haze/80">
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-steel">建议程序</p>
                    <div className="mt-3 space-y-2 text-sm text-haze/80">
                      {financialAnalysis.recommended_procedures.map((item) => (
                        <p key={item}>{item}</p>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                财报专项区只展示聚合后的异常、重点科目和建议程序，不自动展开文档明细。
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
