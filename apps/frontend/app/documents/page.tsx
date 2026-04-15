"use client";

import { useEffect, useMemo, useState } from "react";
import type { DocumentExtractItem, DocumentListItem } from "@auditpilot/shared-types";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
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

const PARSE_STATUS_LABELS: Record<string, string> = {
  uploaded: "已上传",
  parsing: "解析中",
  parsed: "已解析",
  failed: "解析失败",
};

const ANALYSIS_STATUS_LABELS: Record<string, string> = {
  pending: "待分析",
  running: "分析运行中",
  succeeded: "分析完成",
  partial_fallback: "部分回退",
  failed: "分析失败",
};

const ANALYSIS_MODE_LABELS: Record<string, string> = {
  llm_primary: "MiniMax 主链",
  hybrid_fallback: "LLM + 规则回退",
  rule_only: "规则兜底",
};

const EMPTY_REASON_LABELS: Record<string, string> = {
  no_sync_run: "该企业当前还没有执行过官方同步，请先触发同步或上传 PDF。",
  generic_window_no_documents: "当前同步窗口内没有命中官方文档，建议手动刷新或重新同步。",
  annual_package_not_published: "最近一套年报包暂未披露，或当前检索窗口内尚未命中。",
  provider_returned_only_other: "当前窗口只抓到非文档公告，尚未抓到年报、审计报告或内控报告。",
  provider_error: "官方同步过程中出现上游错误，本次未能产出文档。",
};

function renderStructuredFields(extract: DocumentExtractItem) {
  const rows: string[] = [];
  if (extract.metric_name) {
    rows.push(`数值：${extract.metric_name} ${extract.metric_value ?? "-"} ${extract.metric_unit ?? ""}`.trim());
  }
  if (extract.event_type) {
    rows.push(`事件：${extract.event_type}`);
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

export default function DocumentsPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError, invalidateEnterpriseResources } = useEnterpriseContext();
  const {
    data: readiness,
    loading: readinessLoading,
    error: readinessError,
    refresh: refreshReadiness,
  } = useReadinessResource(currentEnterpriseId);
  const { data: documents, loading, error, refresh } = useDocumentsResource(currentEnterpriseId);
  const { data: financialAnalysis, refresh: refreshFinancialAnalysis } = useFinancialAnalysisResource(currentEnterpriseId);

  const [file, setFile] = useState<File | null>(null);
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);
  const [extracts, setExtracts] = useState<DocumentExtractItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("支持 PDF 或文本文件。文档解析会显示规则命中、结构化字段和财报专项结果。");
  const [syncGapRetryCount, setSyncGapRetryCount] = useState(0);

  useEffect(() => {
    setActiveDocumentId(null);
    setExtracts([]);
    setFile(null);
    setSyncGapRetryCount(0);
  }, [currentEnterpriseId]);

  useEffect(() => {
    if (
      !currentEnterpriseId ||
      loading ||
      readinessLoading ||
      error ||
      readinessError ||
      (documents?.length ?? 0) > 0 ||
      (readiness?.official_doc_count ?? 0) === 0 ||
      syncGapRetryCount > 0
    ) {
      return;
    }

    const timer = window.setTimeout(() => {
      setSyncGapRetryCount(1);
      void Promise.allSettled([refreshReadiness(), refresh(), refreshFinancialAnalysis()]);
    }, 1500);

    return () => window.clearTimeout(timer);
  }, [
    currentEnterpriseId,
    documents,
    error,
    loading,
    readiness,
    readinessError,
    readinessLoading,
    refresh,
    refreshFinancialAnalysis,
    refreshReadiness,
    syncGapRetryCount,
  ]);

  const activeDocument = useMemo(
    () => documents?.find((item) => item.id === activeDocumentId) ?? null,
    [activeDocumentId, documents],
  );

  const financialDocuments = financialAnalysis?.documents ?? [];
  const hasSyncGap = Boolean(
    currentEnterpriseId &&
      !loading &&
      !readinessLoading &&
      !error &&
      !readinessError &&
      (documents?.length ?? 0) === 0 &&
      (readiness?.official_doc_count ?? 0) > 0,
  );
  const readinessEmptyMessage =
    readiness?.empty_reason && EMPTY_REASON_LABELS[readiness.empty_reason]
      ? EMPTY_REASON_LABELS[readiness.empty_reason]
      : "当前企业暂无文档。可先同步官方公告或上传 PDF。";
  const lastSyncWindow = readiness?.last_sync_diagnostics?.initial_window;
  const annualTargetYears = readiness?.last_sync_diagnostics?.annual_package_target_years ?? [];

  const refreshAll = async () => {
    await Promise.allSettled([refreshReadiness(), refresh(), refreshFinancialAnalysis()]);
  };

  const upload = async () => {
    if (!file || !currentEnterpriseId) return;
    setBusy(true);
    try {
      const result = await api.uploadDocument(currentEnterpriseId, file);
      invalidateEnterpriseResources(currentEnterpriseId, ["documents", "readiness", "financialAnalysis"]);
      await refreshAll();
      setActiveDocumentId(result.id);
      setMessage(`文档 ${result.document_name} 上传成功。`);
    } catch (uploadError) {
      setMessage(uploadError instanceof Error ? uploadError.message : "文档上传失败。");
    } finally {
      setBusy(false);
    }
  };

  const parse = async (document: DocumentListItem) => {
    setBusy(true);
    try {
      await api.parseDocument(document.id);
      const response = await api.getDocumentExtracts(document.id);
      invalidateEnterpriseResources(currentEnterpriseId ?? 0, ["documents", "readiness", "financialAnalysis"]);
      await refreshAll();
      setActiveDocumentId(document.id);
      setExtracts(response.extracts);
      setMessage(`已生成 ${response.extracts.length} 条结构化抽取结果。`);
    } catch (parseError) {
      setMessage(parseError instanceof Error ? parseError.message : "文档解析失败。");
    } finally {
      setBusy(false);
    }
  };

  const loadExtracts = async (document: DocumentListItem) => {
    setBusy(true);
    try {
      const response = await api.getDocumentExtracts(document.id);
      setActiveDocumentId(document.id);
      setExtracts(response.extracts);
      setMessage(`已加载 ${document.document_name} 的抽取结果。`);
    } catch (loadError) {
      setMessage(loadError instanceof Error ? loadError.message : "抽取结果加载失败。");
    } finally {
      setBusy(false);
    }
  };

  const updateClassification = async (document: DocumentListItem, classifiedType: string) => {
    setBusy(true);
    try {
      await api.overrideDocumentClassification(document.id, classifiedType);
      invalidateEnterpriseResources(currentEnterpriseId ?? 0, ["documents", "financialAnalysis"]);
      await Promise.allSettled([refresh(), refreshFinancialAnalysis()]);
      if (activeDocumentId === document.id) {
        await loadExtracts(document);
      }
      setMessage(`已将文档分类修正为 ${classifiedType}。`);
    } catch (classificationError) {
      setMessage(classificationError instanceof Error ? classificationError.message : "文档分类修正失败。");
    } finally {
      setBusy(false);
    }
  };

  const updateEventType = async (extract: DocumentExtractItem, eventType: string) => {
    if (!activeDocumentId || !extract.evidence_span_id) return;
    setBusy(true);
    try {
      await api.overrideExtractEventType(activeDocumentId, extract.evidence_span_id, eventType);
      const response = await api.getDocumentExtracts(activeDocumentId);
      setExtracts(response.extracts);
      setMessage(`已将事件类型修正为 ${eventType}。`);
    } catch (eventError) {
      setMessage(eventError instanceof Error ? eventError.message : "事件类型修正失败。");
    } finally {
      setBusy(false);
    }
  };

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
            <Button variant="outline" onClick={() => void refreshAll()} disabled={busy}>
              刷新文档
            </Button>
            <Button onClick={upload} disabled={!file || !currentEnterpriseId || busy}>
              {busy ? "处理中..." : "上传文档"}
            </Button>
          </div>
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
      ) : loading || readinessLoading ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">正在加载企业文档列表...</div>
        </Card>
      ) : error || readinessError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
            {error ?? readinessError}
          </div>
        </Card>
      ) : hasSyncGap ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
            {syncGapRetryCount === 0 ? "官方文档已存在，列表正在同步刷新..." : "暂未同步完成，请手动刷新。"}
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
                            {document.classified_type ?? document.document_type} |{" "}
                            {PARSE_STATUS_LABELS[document.parse_status] ?? document.parse_status} | {document.source}
                          </p>
                          <p className="mt-2 text-xs text-haze/65">
                            版本：{document.latest_extract_version ?? "pending"} | 抽取族：{" "}
                            {document.extract_family_summary?.join(" / ") || "未生成"} | 事件覆盖：{" "}
                            {document.event_coverage?.join(" / ") || "无"}
                          </p>
                          <p className="mt-2 text-xs text-haze/65">
                            分析状态：{ANALYSIS_STATUS_LABELS[document.analysis_status ?? ""] ?? (document.analysis_status ?? "pending")} |{" "}
                            {ANALYSIS_MODE_LABELS[document.analysis_mode ?? ""] ?? (document.analysis_mode ?? "待生成")}
                          </p>
                          {document.analysis_groups?.length ? (
                            <p className="mt-2 text-xs text-haze/65">分析分组：{document.analysis_groups.join(" / ")}</p>
                          ) : null}
                          {document.last_error_message ? (
                            <p className="mt-2 text-xs text-amber-200">
                              最近错误：{document.last_error_message}
                              {document.last_error_at ? ` | ${document.last_error_at}` : ""}
                            </p>
                          ) : null}
                        </div>
                        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
                          <select
                            className="rounded-2xl border border-white/10 bg-black/10 px-3 py-2 text-sm text-haze/80"
                            value={document.classified_type ?? document.document_type}
                            onChange={(event) => void updateClassification(document, event.target.value)}
                            disabled={busy}
                          >
                            {CLASSIFICATION_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                          <Button variant="outline" onClick={() => void loadExtracts(document)} disabled={busy}>
                            查看抽取
                          </Button>
                          <Button onClick={() => void parse(document)} disabled={busy || document.parse_status === "parsing"}>
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
                  {lastSyncWindow ? (
                    <p className="mt-2 text-xs text-haze/60">
                      最近同步窗口：{lastSyncWindow.date_from} ~ {lastSyncWindow.date_to}
                    </p>
                  ) : null}
                  {annualTargetYears.length > 0 ? (
                    <p className="mt-2 text-xs text-haze/60">年报包补抓年份：{annualTargetYears.join(" / ")}</p>
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
                              <p className="font-medium text-white">{extract.title}</p>
                              <p className="mt-2 text-sm text-haze/80">{extract.problem_summary}</p>
                              <div className="mt-3 flex flex-wrap gap-2 text-xs text-haze/65">
                                <span>{extract.extract_family ?? extract.extract_type}</span>
                                <span>{extract.detail_level === "financial_deep_dive" ? "财报深析" : "通用抽取"}</span>
                                {extract.section_title ? <span>{extract.section_title}</span> : null}
                                {extract.page_start || extract.page_end ? (
                                  <span>
                                    页码：{extract.page_start ?? "?"}-{extract.page_end ?? extract.page_start ?? "?"}
                                  </span>
                                ) : null}
                              </div>
                            </div>
                          </div>
                        </summary>
                        <div className="mt-4 space-y-4 border-t border-white/10 pt-4">
                          <section>
                            <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">规则与风险键</p>
                            <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-haze/80">
                              <p>规则：{extract.applied_rules.length ? extract.applied_rules.join(" / ") : "未命中"}</p>
                              {extract.canonical_risk_key ? <p className="mt-2">风险键：{extract.canonical_risk_key}</p> : null}
                            </div>
                          </section>
                          <section>
                            <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">证据摘要</p>
                            <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-haze/80">
                              {extract.evidence_excerpt}
                            </div>
                          </section>
                          {(extract.event_type || extract.opinion_type) && activeDocumentId ? (
                            <section>
                              <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">事件 / 意见修正</p>
                              <select
                                className="rounded-2xl border border-white/10 bg-black/10 px-3 py-2 text-sm text-haze/80"
                                value={extract.event_type ?? extract.opinion_type ?? ""}
                                onChange={(event) => void updateEventType(extract, event.target.value)}
                                disabled={busy || !extract.evidence_span_id}
                              >
                                <option value="">请选择</option>
                                {EVENT_OPTIONS.map((option) => (
                                  <option key={option} value={option}>
                                    {option}
                                  </option>
                                ))}
                              </select>
                            </section>
                          ) : null}
                          {structuredRows.length > 0 ? (
                            <section>
                              <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">结构化字段</p>
                              <div className="space-y-2 rounded-2xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-haze/80">
                                {structuredRows.map((row) => (
                                  <p key={row}>{row}</p>
                                ))}
                              </div>
                            </section>
                          ) : null}
                        </div>
                      </details>
                    );
                  })}
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                  暂无抽取结果。请选择文档查看，或先执行解析。
                </div>
              )}
            </Card>
          </div>

          <Card>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">财报专项</p>
            <p className="mt-2 text-sm text-haze/75">{financialAnalysis?.summary ?? "当前尚未生成财报专项分析。"}</p>
            {financialDocuments.length > 0 ? (
              <div className="mt-4 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                <div className="space-y-3">
                  {financialDocuments.map((document) => (
                    <div key={document.document_id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="font-medium text-white">{document.document_name}</p>
                      <p className="mt-2 text-xs text-haze/65">
                        {document.classified_type} | {document.analysis_status ?? "unknown"} | {document.analysis_mode ?? "unknown"}
                      </p>
                      <p className="mt-2 text-sm text-haze/80">
                        异常条数：{document.anomalies.length} | 指标条数：{document.key_metrics.length}
                      </p>
                      {document.anomalies.slice(0, 2).map((item) => (
                        <div key={`${document.document_id}-${item.title}`} className="mt-3 rounded-2xl border border-white/10 bg-black/10 p-3 text-sm text-haze/80">
                          <p className="font-medium text-white">{item.title}</p>
                          <p className="mt-2">{item.summary}</p>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
                <div className="space-y-4">
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-steel">重点科目</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {(financialAnalysis?.focus_accounts ?? []).map((item) => (
                        <span key={item} className="rounded-full bg-black/10 px-3 py-1 text-xs text-haze/80">
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-steel">建议程序</p>
                    <div className="mt-3 space-y-2 text-sm text-haze/80">
                      {(financialAnalysis?.recommended_procedures ?? []).map((item) => (
                        <p key={item}>{item}</p>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                只有年报、审计报告或内控报告中存在财报深析抽取时，才会显示这里的专项结果。
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
