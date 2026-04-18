"use client";

import type { DocumentExtractItem, DocumentListItem } from "@auditpilot/shared-types";

import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  formatAnalysisGroup,
  formatAnalysisMode,
  formatAnalysisStatus,
  formatCanonicalRiskKey,
  formatDocumentType,
  formatEventType,
  formatKnownLabel,
  formatParseStatus,
  formatRuleCode,
  formatSourceName,
} from "@/lib/display-labels";

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

export function DocumentDetailPanel({
  document,
  extracts,
  busy,
  classificationOptions,
  eventOptions,
  onUpdateClassification,
  onUpdateEventType,
}: {
  document: DocumentListItem | null;
  extracts: DocumentExtractItem[];
  busy: boolean;
  classificationOptions: string[];
  eventOptions: string[];
  onUpdateClassification: (document: DocumentListItem, classifiedType: string) => void;
  onUpdateEventType: (extract: DocumentExtractItem, eventType: string) => void;
}) {
  if (!document) {
    return (
      <div className="flex h-full min-h-[480px] items-center justify-center rounded-xl border border-dashed bg-muted/30 px-6 text-sm text-muted-foreground">
        当前未读取任何文档抽取结果。点击左侧“查看抽取”后再进入详情。
      </div>
    );
  }

  return (
    <Tabs defaultValue="basic" className="h-full">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold text-foreground">{document.document_name}</p>
          <p className="mt-1 text-sm text-muted-foreground">{formatSourceName(document.source)}</p>
        </div>
        <Badge value={document.parse_status} label={formatParseStatus(document.parse_status)} />
      </div>

      <TabsList className="mt-4 grid w-full grid-cols-3">
        <TabsTrigger value="basic">基本信息</TabsTrigger>
        <TabsTrigger value="extracts">抽取结果</TabsTrigger>
        <TabsTrigger value="adjustments">人工修正</TabsTrigger>
      </TabsList>

      <TabsContent value="basic" className="space-y-4">
        <div className="rounded-xl border bg-muted/20 p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">文档分类</p>
              <p className="mt-2 text-sm text-foreground">
                {formatDocumentType(document.classified_type ?? document.document_type)}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">分析模式</p>
              <p className="mt-2 text-sm text-foreground">{formatAnalysisMode(document.analysis_mode)}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">分析状态</p>
              <p className="mt-2 text-sm text-foreground">{formatAnalysisStatus(document.analysis_status)}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">最近更新时间</p>
              <p className="mt-2 text-sm text-foreground">{formatTimestamp(document.analyzed_at ?? document.created_at)}</p>
            </div>
          </div>
          {document.analysis_groups?.length ? (
            <>
              <Separator className="my-4" />
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">分析分组</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {document.analysis_groups.map((group) => (
                    <Badge key={group} value="default" label={formatAnalysisGroup(group)} />
                  ))}
                </div>
              </div>
            </>
          ) : null}
          {document.last_error_message ? (
            <>
              <Separator className="my-4" />
              <div className="text-sm text-amber-700">
                最近错误：{document.last_error_message}
                {document.last_error_at ? ` | ${formatTimestamp(document.last_error_at)}` : ""}
              </div>
            </>
          ) : null}
        </div>
      </TabsContent>

      <TabsContent value="extracts" className="space-y-3">
        {extracts.length > 0 ? (
          extracts.map((extract, index) => {
            const structuredRows = renderStructuredFields(extract);
            return (
              <div key={extract.id} className="rounded-xl border bg-background p-4">
                <div className="flex items-start gap-3">
                  <span className="pt-0.5 text-sm font-semibold text-primary">{index + 1}.</span>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-foreground">{formatKnownLabel(extract.title)}</p>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">{extract.problem_summary}</p>
                  </div>
                </div>
                <div className="mt-4 space-y-4">
                  <div className="rounded-lg bg-muted/40 p-3 text-sm text-foreground">
                    {extract.applied_rules.length ? (
                      <p>规则：{extract.applied_rules.map((item) => formatRuleCode(item)).join(" / ")}</p>
                    ) : (
                      <p>规则：未命中</p>
                    )}
                    {extract.canonical_risk_key ? (
                      <p className="mt-2">风险键：{formatCanonicalRiskKey(extract.canonical_risk_key)}</p>
                    ) : null}
                  </div>
                  <div>
                    <p className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">证据摘要</p>
                    <div className="rounded-lg bg-muted/40 p-3 text-sm leading-6 text-foreground">
                      {extract.evidence_excerpt}
                    </div>
                  </div>
                  {structuredRows.length ? (
                    <div>
                      <p className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">结构化字段</p>
                      <div className="space-y-2 text-sm text-muted-foreground">
                        {structuredRows.map((row) => (
                          <p key={row}>{row}</p>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })
        ) : (
          <div className="rounded-xl border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
            当前文档还没有抽取结果。
          </div>
        )}
      </TabsContent>

      <TabsContent value="adjustments" className="space-y-4">
        <div className="rounded-xl border bg-muted/20 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">文档分类修正</p>
          <div className="mt-3">
            <Select
              value={document.classified_type ?? document.document_type}
              onValueChange={(value) => onUpdateClassification(document, value)}
              disabled={busy}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {classificationOptions.map((option) => (
                  <SelectItem key={option} value={option}>
                    {formatDocumentType(option)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="rounded-xl border bg-muted/20 p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">事件类型修正</p>
          {extracts.filter((extract) => extract.evidence_span_id).length > 0 ? (
            <div className="mt-3 space-y-3">
              {extracts
                .filter((extract) => extract.evidence_span_id)
                .map((extract) => (
                  <div key={extract.id} className="rounded-lg border bg-background p-3">
                    <p className="text-sm font-medium text-foreground">{formatKnownLabel(extract.title)}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{extract.problem_summary}</p>
                    <div className="mt-3">
                      <Select value={extract.event_type ?? undefined} onValueChange={(value) => onUpdateEventType(extract, value)} disabled={busy}>
                        <SelectTrigger>
                          <SelectValue placeholder="请选择事件类型" />
                        </SelectTrigger>
                        <SelectContent>
                          {eventOptions.map((option) => (
                            <SelectItem key={option} value={option}>
                              {formatEventType(option)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">当前文档没有可人工修正的事件抽取。</p>
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
}
