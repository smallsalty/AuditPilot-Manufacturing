"use client";

import { useEffect, useMemo, useState } from "react";
import type { AnnouncementRiskItem, DocumentExtractItem, DocumentListItem } from "@auditpilot/shared-types";

import { AnnouncementRawEventsTable } from "@/components/documents/announcement-raw-events-table";
import { AnnouncementRiskList } from "@/components/documents/announcement-risk-list";
import { AnnouncementRiskSummaryPanel } from "@/components/documents/announcement-risk-summary-panel";
import { DocumentDetailPanel } from "@/components/documents/document-detail-panel";
import { DocumentFinancialPanel } from "@/components/documents/document-financial-panel";
import { DocumentsTable } from "@/components/documents/documents-table";
import { DocumentsToolbar } from "@/components/documents/documents-toolbar";
import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card } from "@/components/ui/card";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api } from "@/lib/api";
import { useDocumentsResource, useEventsResource, useFinancialAnalysisResource, useReadinessResource } from "@/lib/enterprise-resources";

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
  const { data: enterpriseEvents, loading: eventsLoading, error: eventsError, refresh: refreshEvents } =
    useEventsResource(currentEnterpriseId);

  const [file, setFile] = useState<File | null>(null);
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);
  const [activeEventId, setActiveEventId] = useState<number | null>(null);
  const [activeEventFallbackKey, setActiveEventFallbackKey] = useState<string | null>(null);
  const [extracts, setExtracts] = useState<DocumentExtractItem[]>([]);
  const [message, setMessage] = useState("支持 PDF 或文本文件。文档需手动解析，解析结果会显示规则命中、结构化字段和财报专项结果。");
  const [syncGapRetryCount, setSyncGapRetryCount] = useState(0);
  const [pageAction, setPageAction] = useState<PageAction>({ kind: "idle" });
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [detailSheetOpen, setDetailSheetOpen] = useState(false);

  useEffect(() => {
    setActiveDocumentId(null);
    setActiveEventId(null);
    setActiveEventFallbackKey(null);
    setExtracts([]);
    setFile(null);
    setSyncGapRetryCount(0);
    setPageAction({ kind: "idle" });
    setUploadDialogOpen(false);
    setDetailSheetOpen(false);
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
      void Promise.allSettled([refreshReadiness(), refreshDocuments(), refreshEvents(), refreshFinancialAnalysis()]).finally(() => {
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
    refreshEvents,
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

  const eventRiskSummary = enterpriseEvents?.risk_summary ?? null;
  const announcementRisks = eventRiskSummary?.announcement_risks ?? [];
  const rawEvents = enterpriseEvents?.raw_events ?? [];

  const refreshAll = async () => {
    setPageAction({ kind: "reading", message: "正在读取当前企业的文档与财报专项结果..." });
    await Promise.allSettled([
      refreshReadiness({ force: true }),
      refreshDocuments({ force: true }),
      refreshEvents({ force: true }),
      refreshFinancialAnalysis({ force: true }),
    ]);
    setPageAction({ kind: "idle" });
  };

  const focusAnnouncementRisk = (risk: AnnouncementRiskItem) => {
    setActiveEventId(risk.source_event_id ?? null);
    setActiveEventFallbackKey(`${risk.source_title}::${risk.source_date ?? ""}`);
  };

  const loadExtracts = async (document: DocumentListItem, mode: PageAction["kind"] = "reading") => {
    const readingMessage = mode === "analyzing" ? "正在刷新抽取结果..." : "正在读取文档抽取结果...";
    setPageAction({ kind: mode, message: readingMessage });
    try {
      const response = await api.getDocumentExtracts(document.id);
      setActiveDocumentId(document.id);
      setExtracts(response.extracts);
      setDetailSheetOpen(true);
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
      setUploadDialogOpen(false);
      setFile(null);
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
      await Promise.allSettled([
        refreshReadiness({ force: true }),
        refreshDocuments({ force: true }),
        refreshFinancialAnalysis({ force: true }),
      ]);
      setActiveDocumentId(document.id);
      setExtracts(response.extracts);
      setDetailSheetOpen(true);
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
      await Promise.allSettled([
        refreshDocuments({ force: true }),
        refreshFinancialAnalysis({ force: true }),
        refreshReadiness({ force: true }),
      ]);
      if (activeDocumentId === document.id) {
        await loadExtracts(document, "analyzing");
      }
      setMessage(`已将文档分类修正为 ${classifiedType}。`);
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
      setMessage(`已将事件类型修正为 ${eventType || "未指定"}。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "事件类型修正失败。");
    } finally {
      setPageAction({ kind: "idle" });
    }
  };

  const topStatus = useMemo(() => {
    if (pageAction.kind === "analyzing") {
      return { label: "分析中", message: pageAction.message, variant: "warning" as const };
    }
    if (pageAction.kind === "reading" || documentsLoading || readinessLoading || financialAnalysisLoading) {
      return {
        label: "读取中",
        message:
          pageAction.kind === "reading"
            ? pageAction.message
            : "正在读取当前企业的文档、就绪状态和财报专项结果...",
        variant: "default" as const,
      };
    }
    if (readiness?.manual_parse_required) {
      const count = readiness.documents_pending_parse ?? 0;
      return {
        label: "已同步，待手动解析",
        message: count > 0 ? `已同步 ${count} 份待解析文档，请手动点击“解析”或“查看抽取”。` : "官方文档已同步，待手动解析。",
        variant: "default" as const,
      };
    }
    if (hasSyncGap) {
      return {
        label: "同步/刷新中",
        message: syncGapRetryCount === 0 ? "官方文档已存在，列表正在同步刷新..." : "同步仍在收尾，请手动刷新。",
        variant: "default" as const,
      };
    }
    return {
      label: "空闲",
      message,
      variant: "default" as const,
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
        <DocumentsToolbar
          enterpriseName={currentEnterprise?.name}
          currentEnterpriseId={currentEnterpriseId}
          officialDocCount={readiness?.official_doc_count ?? 0}
          message={message}
          uploadOpen={uploadDialogOpen}
          onUploadOpenChange={setUploadDialogOpen}
          fileName={file?.name ?? null}
          onFileChange={setFile}
          onRefresh={() => void refreshAll()}
          onUpload={() => void upload()}
          disabled={pageAction.kind !== "idle"}
          uploadDisabled={!file || !currentEnterpriseId || pageAction.kind !== "idle"}
        />
      </Card>

      <Alert variant={topStatus.variant}>
        <AlertTitle>{topStatus.label}</AlertTitle>
        <AlertDescription>{topStatus.message}</AlertDescription>
      </Alert>

      {enterpriseError ? (
        <Alert variant="destructive">
          <AlertTitle>企业上下文不可用</AlertTitle>
          <AlertDescription>{enterpriseError}</AlertDescription>
        </Alert>
      ) : !currentEnterpriseId ? (
        <Alert>
          <AlertTitle>请先选择企业</AlertTitle>
          <AlertDescription>当前没有可用企业。</AlertDescription>
        </Alert>
      ) : documentsError || readinessError || financialAnalysisError ? (
        <Alert variant="destructive">
          <AlertTitle>文档中心加载失败</AlertTitle>
          <AlertDescription>{documentsError ?? readinessError ?? financialAnalysisError}</AlertDescription>
        </Alert>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Card className="p-5">
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">官方文档</p>
              <p className="mt-3 text-3xl font-semibold text-foreground">{readiness?.official_doc_count ?? 0}</p>
              <p className="mt-2 text-sm text-muted-foreground">同步后进入当前企业文档池的文档数量。</p>
            </Card>
            <Card className="p-5">
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">待手动解析</p>
              <p className="mt-3 text-3xl font-semibold text-foreground">{readiness?.documents_pending_parse ?? 0}</p>
              <p className="mt-2 text-sm text-muted-foreground">仍需手动点击“解析”的文档数量。</p>
            </Card>
            <Card className="p-5">
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">已读取列表</p>
              <p className="mt-3 text-3xl font-semibold text-foreground">{documents?.length ?? 0}</p>
              <p className="mt-2 text-sm text-muted-foreground">当前文档列表中的可操作文档数量。</p>
            </Card>
            <Card className="p-5">
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">同步状态</p>
              <p className="mt-3 text-3xl font-semibold text-foreground">{readiness?.sync_status ?? "暂无"}</p>
              <p className="mt-2 text-sm text-muted-foreground">最近同步：{readiness?.last_sync_at ?? "暂无"}</p>
            </Card>
          </div>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
            <Card className="p-0">
              <div className="border-b px-6 py-5">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">文档主列表</p>
                <p className="mt-2 text-sm text-muted-foreground">优先查看分类、解析状态和抽取入口。</p>
              </div>
              <div className="p-6">
                {documents && documents.length > 0 ? (
                  <DocumentsTable
                    documents={documents}
                    activeDocumentId={activeDocumentId}
                    busy={pageAction.kind !== "idle"}
                    onView={(document) => void loadExtracts(document)}
                    onParse={(document) => void parse(document)}
                  />
                ) : (
                  <div className="rounded-xl border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
                    <p>{readinessEmptyMessage}</p>
                    {readiness?.manual_parse_required ? (
                      <p className="mt-2 text-xs text-muted-foreground">
                        已同步 {readiness.documents_pending_parse} 份官方文档，待手动解析。
                      </p>
                    ) : null}
                    {readiness?.last_sync_diagnostics?.initial_window ? (
                      <p className="mt-2 text-xs text-muted-foreground">
                        最近同步窗口：{readiness.last_sync_diagnostics.initial_window.date_from} ~{" "}
                        {readiness.last_sync_diagnostics.initial_window.date_to}
                      </p>
                    ) : null}
                  </div>
                )}
              </div>
            </Card>

            <Card className="hidden min-h-[720px] xl:block">
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">文档详情</p>
              <p className="mt-2 text-sm text-muted-foreground">查看当前文档的抽取结果和人工修正入口。</p>
              <div className="mt-5">
                <DocumentDetailPanel
                  document={activeDocument}
                  extracts={extracts}
                  busy={pageAction.kind !== "idle"}
                  classificationOptions={CLASSIFICATION_OPTIONS}
                  eventOptions={EVENT_OPTIONS}
                  onUpdateClassification={(document, classifiedType) => void updateClassification(document, classifiedType)}
                  onUpdateEventType={(extract, eventType) => void updateEventType(extract, eventType)}
                />
              </div>
            </Card>
          </div>

          <div className="xl:hidden">
            <Sheet open={detailSheetOpen} onOpenChange={setDetailSheetOpen}>
              <SheetContent side="right" className="w-full overflow-y-auto p-6 sm:max-w-2xl">
                <SheetHeader>
                  <SheetTitle>文档详情</SheetTitle>
                  <SheetDescription>查看抽取结果与人工修正入口。</SheetDescription>
                </SheetHeader>
                <div className="mt-4">
                  <DocumentDetailPanel
                    document={activeDocument}
                    extracts={extracts}
                    busy={pageAction.kind !== "idle"}
                    classificationOptions={CLASSIFICATION_OPTIONS}
                    eventOptions={EVENT_OPTIONS}
                    onUpdateClassification={(document, classifiedType) => void updateClassification(document, classifiedType)}
                    onUpdateEventType={(extract, eventType) => void updateEventType(extract, eventType)}
                  />
                </div>
              </SheetContent>
            </Sheet>
          </div>

          <Card>
            <div className="space-y-5">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">公告事件</p>
                <p className="mt-2 text-sm text-muted-foreground">
                  展示已同步公告事件的解释结果和原始事件明细，不改现有评分与风险主链路。
                </p>
              </div>

              {eventsError ? (
                <Alert variant="destructive">
                  <AlertTitle>公告事件加载失败</AlertTitle>
                  <AlertDescription>公告事件加载失败，请稍后刷新</AlertDescription>
                </Alert>
              ) : eventsLoading ? (
                <div className="rounded-xl border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
                  正在读取已同步公告事件...
                </div>
              ) : rawEvents.length === 0 && announcementRisks.length === 0 ? (
                <div className="rounded-xl border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
                  当前企业暂无已同步公告事件
                </div>
              ) : (
                <div className="space-y-6">
                  {announcementRisks.length > 0 && eventRiskSummary ? (
                    <>
                      <AnnouncementRiskSummaryPanel riskSummary={eventRiskSummary} />
                      <div className="space-y-3">
                        <div>
                          <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">事件解释层</p>
                          <p className="mt-2 text-sm text-muted-foreground">
                            基于现有公告匹配、分层评分和解释逻辑生成，用于说明为什么该事件值得审计关注。
                          </p>
                        </div>
                        <AnnouncementRiskList
                          risks={announcementRisks}
                          activeEventId={activeEventId}
                          activeFallbackKey={activeEventFallbackKey}
                          onSelectRisk={focusAnnouncementRisk}
                        />
                      </div>
                    </>
                  ) : (
                    <Alert>
                      <AlertTitle>事件解释暂未生成</AlertTitle>
                      <AlertDescription>已同步公告事件，运行风险分析后生成事件解释</AlertDescription>
                    </Alert>
                  )}

                  <div className="space-y-3">
                    <div>
                      <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">原始事件层</p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        按同步结果展示原始公告事件，用于核对标题命中、严重程度和来源链接。
                      </p>
                    </div>
                    {rawEvents.length > 0 ? (
                      <AnnouncementRawEventsTable
                        events={rawEvents}
                        activeEventId={activeEventId}
                        activeFallbackKey={activeEventFallbackKey}
                      />
                    ) : (
                      <div className="rounded-xl border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
                        当前企业暂无已同步公告事件
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </Card>

          <Card>
            <DocumentFinancialPanel financialAnalysis={financialAnalysis} loading={financialAnalysisLoading} />
          </Card>
        </>
      )}
    </div>
  );
}
