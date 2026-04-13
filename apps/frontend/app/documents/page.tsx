"use client";

import { useEffect, useMemo, useState } from "react";
import type { DocumentExtractItem, DocumentListItem } from "@auditpilot/shared-types";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useDocumentsResource, useReadinessResource } from "@/lib/enterprise-resources";

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

export default function DocumentsPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError, invalidateEnterpriseResources } = useEnterpriseContext();
  const { data: readiness } = useReadinessResource(currentEnterpriseId);
  const { data: documents, loading, error, refresh } = useDocumentsResource(currentEnterpriseId);
  const [file, setFile] = useState<File | null>(null);
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);
  const [extracts, setExtracts] = useState<DocumentExtractItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("支持 PDF 或文本文件。抽取结果会展示问题概述、证据位置、规则命中和事件字段。");

  useEffect(() => {
    setActiveDocumentId(null);
    setExtracts([]);
    setFile(null);
  }, [currentEnterpriseId]);

  const activeDocument = useMemo(
    () => documents?.find((item) => item.id === activeDocumentId) ?? null,
    [activeDocumentId, documents],
  );

  const upload = async () => {
    if (!file || !currentEnterpriseId) return;
    setBusy(true);
    try {
      const result = await api.uploadDocument(currentEnterpriseId, file);
      invalidateEnterpriseResources(currentEnterpriseId, ["documents", "readiness"]);
      await refresh();
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
      invalidateEnterpriseResources(currentEnterpriseId ?? 0, ["documents", "readiness"]);
      await refresh();
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
      invalidateEnterpriseResources(currentEnterpriseId ?? 0, ["documents"]);
      await refresh();
      if (activeDocumentId === document.id) {
        await loadExtracts(document);
      }
      setMessage(`已将文档分型修正为 ${classifiedType}。`);
    } catch (classificationError) {
      setMessage(classificationError instanceof Error ? classificationError.message : "文档分型修正失败。");
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
        <p className="text-xs uppercase tracking-[0.24em] text-steel">文档中心</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">{currentEnterprise ? `${currentEnterprise.name} 文档中心` : "文档中心"}</h2>
        <p className="mt-2 text-haze/75">{message}</p>
        {currentEnterprise ? <p className="mt-3 text-sm text-haze/65">当前企业官方文档：{readiness?.official_doc_count ?? 0} 份</p> : null}
        <div className="mt-5 flex flex-col gap-3 lg:flex-row">
          <input type="file" accept=".pdf,.txt" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-haze/75" />
          <Button onClick={upload} disabled={!file || !currentEnterpriseId || busy}>{busy ? "处理中..." : "上传文档"}</Button>
        </div>
      </Card>

      {enterpriseError ? (
        <Card><div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">企业列表加载失败：{enterpriseError}</div></Card>
      ) : !currentEnterpriseId ? (
        <Card><div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">请先选择企业。</div></Card>
      ) : loading ? (
        <Card><div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">正在加载企业文档列表...</div></Card>
      ) : error ? (
        <Card><div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">文档列表加载失败：{error}</div></Card>
      ) : (
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
                          {document.classified_type ?? document.document_type} | {PARSE_STATUS_LABELS[document.parse_status] ?? document.parse_status} | {document.source}
                        </p>
                        <p className="mt-2 text-xs text-haze/65">
                          版本：{document.latest_extract_version ?? "pending"} | 抽取家族：{document.extract_family_summary?.join(" / ") || "未生成"} | 事件覆盖：{document.event_coverage?.join(" / ") || "无"}
                        </p>
                      </div>
                      <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
                        <select
                          className="rounded-2xl border border-white/10 bg-black/10 px-3 py-2 text-sm text-haze/80"
                          value={document.classified_type ?? document.document_type}
                          onChange={(event) => void updateClassification(document, event.target.value)}
                          disabled={busy}
                        >
                          {CLASSIFICATION_OPTIONS.map((option) => (
                            <option key={option} value={option}>{option}</option>
                          ))}
                        </select>
                        <Button variant="outline" onClick={() => void loadExtracts(document)} disabled={busy}>查看抽取</Button>
                        <Button onClick={() => void parse(document)} disabled={busy || document.parse_status === "parsing"}>
                          {document.parse_status === "parsed" ? "重新解析" : "解析"}
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">当前企业暂无文档。可先同步官方公告或上传 PDF。</div>
            )}
          </Card>
          <Card>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">查看抽取</p>
            {activeDocument ? <p className="mt-2 text-sm text-haze/70">当前文档：{activeDocument.document_name}</p> : null}
            {extracts.length > 0 ? (
              <div className="mt-4 space-y-3">
                {extracts.map((extract, index) => (
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
                            {extract.page_start || extract.page_end ? <span>页码：{extract.page_start ?? "?"}-{extract.page_end ?? extract.page_start ?? "?"}</span> : null}
                          </div>
                        </div>
                      </div>
                    </summary>
                    <div className="mt-4 space-y-4 border-t border-white/10 pt-4">
                      <section>
                        <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">规则与风险键</p>
                        <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-haze/80">
                          {extract.applied_rules.length ? <p>规则：{extract.applied_rules.join(" / ")}</p> : <p>规则：未命中</p>}
                          {extract.canonical_risk_key ? <p className="mt-2">风险键：{extract.canonical_risk_key}</p> : null}
                        </div>
                      </section>
                      <section>
                        <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">证据摘要</p>
                        <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-haze/80">{extract.evidence_excerpt}</div>
                      </section>
                      {(extract.event_type || extract.opinion_type) && activeDocumentId ? (
                        <section>
                          <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">事件/意见修正</p>
                          <select
                            className="rounded-2xl border border-white/10 bg-black/10 px-3 py-2 text-sm text-haze/80"
                            value={extract.event_type ?? extract.opinion_type ?? ""}
                            onChange={(event) => void updateEventType(extract, event.target.value)}
                            disabled={busy || !extract.evidence_span_id}
                          >
                            <option value="">请选择</option>
                            {EVENT_OPTIONS.map((option) => (
                              <option key={option} value={option}>{option}</option>
                            ))}
                          </select>
                        </section>
                      ) : null}
                      {(extract.metric_name || extract.amount || extract.counterparty || extract.conclusion) ? (
                        <section>
                          <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">结构化字段</p>
                          <div className="space-y-2 rounded-2xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-haze/80">
                            {extract.metric_name ? <p>数值：{extract.metric_name} {extract.metric_value ?? "-"} {extract.metric_unit ?? ""}</p> : null}
                            {extract.event_type ? <p>事件：{extract.event_type}</p> : null}
                            {extract.amount != null ? <p>金额：{extract.amount}</p> : null}
                            {extract.counterparty ? <p>对手方：{extract.counterparty}</p> : null}
                            {extract.opinion_type ? <p>意见：{extract.opinion_type}</p> : null}
                            {extract.conclusion ? <p>结论：{extract.conclusion}</p> : null}
                          </div>
                        </section>
                      ) : null}
                    </div>
                  </details>
                ))}
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">暂无抽取结果。请选择文档查看，或先执行解析。</div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
