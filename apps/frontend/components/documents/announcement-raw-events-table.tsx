"use client";

import type { EnterpriseEventItem } from "@auditpilot/shared-types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cleanDisplayText } from "@/lib/display-text";
import { formatEventType, formatKnownLabel } from "@/lib/display-labels";

function formatDate(value?: string | null): string {
  if (!value) {
    return "暂无";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString("zh-CN");
}

function previewList(items?: string[]): string[] {
  return Array.isArray(items) ? items.map((item) => item.trim()).filter(Boolean).slice(0, 3) : [];
}

function hasBodyAnalysis(event: EnterpriseEventItem): boolean {
  const analysis = event.event_analysis;
  return Boolean(analysis?.summary || analysis?.key_facts?.length || analysis?.risk_points?.length || analysis?.audit_focus?.length);
}

function riskScoreFromSeverity(severity: string | null | undefined): number {
  const value = String(severity || "").toLowerCase();
  if (value === "high") {
    return 85;
  }
  if (value === "medium") {
    return 60;
  }
  if (value === "low") {
    return 35;
  }
  return 0;
}

function numberedItems(items: string[]) {
  return (
    <ol className="list-decimal space-y-1 pl-4">
      {items.map((item, index) => (
        <li key={`${index}-${item}`}>{item}</li>
      ))}
    </ol>
  );
}

export function AnnouncementRawEventsTable({
  events,
  activeEventId,
  activeFallbackKey,
  busy,
  parsingEventId,
  onParseEvent,
}: {
  events: EnterpriseEventItem[];
  activeEventId: number | null;
  activeFallbackKey: string | null;
  busy?: boolean;
  parsingEventId?: number | null;
  onParseEvent?: (event: EnterpriseEventItem) => void;
}) {
  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-[34%]">分析链</TableHead>
            <TableHead>事件类型</TableHead>
            <TableHead>风险评分</TableHead>
            <TableHead>主命中类别</TableHead>
            <TableHead>命中关键词</TableHead>
            <TableHead>日期</TableHead>
            <TableHead className="text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.map((event) => {
            const fallbackKey = `${event.title}::${event.event_date ?? ""}`;
            const primaryMatch = event.primary_title_match as { category_name?: string } | null | undefined;
            const keywords = event.title_matches.flatMap((item) => item.matched_keywords).slice(0, 4);
            const isActive = event.id === activeEventId || (activeEventId == null && activeFallbackKey === fallbackKey);
            const analysis = event.event_analysis;
            const keyFacts = previewList(analysis?.key_facts);
            const riskPoints = previewList(analysis?.risk_points);
            const analyzed = hasBodyAnalysis(event);
            const parseLabel = parsingEventId === event.id ? "解析中..." : analyzed ? "重新解析" : "解析";
            const displayTitle = cleanDisplayText(event.title, "暂无标题");
            return (
              <TableRow key={event.id} className={isActive ? "bg-primary/5" : undefined}>
                <TableCell className="align-top">
                  <div className="space-y-2">
                    <div className="rounded-lg border bg-background p-2">
                      <p className="text-xs font-medium text-muted-foreground">公告名称</p>
                      <p className="mt-1 font-medium text-foreground">{displayTitle}</p>
                    </div>
                    <div className="rounded-lg border bg-muted/30 p-2 text-xs text-muted-foreground">
                      <p className="font-medium text-foreground">正文分析</p>
                      {keyFacts.length > 0 ? numberedItems(keyFacts) : <p className="mt-1">待分析</p>}
                      {event.event_analysis_status === "fallback" ? <p className="mt-1">降级结果</p> : null}
                    </div>
                    <div className="rounded-lg border bg-amber-50/60 p-2 text-xs text-amber-900">
                      <p className="font-medium">风险点</p>
                      {riskPoints.length > 0 ? numberedItems(riskPoints) : <p className="mt-1">暂无</p>}
                    </div>
                  </div>
                </TableCell>
                <TableCell className="align-top text-muted-foreground">{formatEventType(event.event_type)}</TableCell>
                <TableCell className="align-top">
                  <Badge value={event.severity.toUpperCase()} label={`${riskScoreFromSeverity(event.severity)}分`} />
                </TableCell>
                <TableCell className="align-top text-muted-foreground">
                  {formatKnownLabel(primaryMatch?.category_name, "暂无")}
                </TableCell>
                <TableCell className="align-top">
                  <div className="flex flex-wrap gap-2">
                    {keywords.length > 0 ? (
                      keywords.map((keyword) => <Badge key={`${event.id}-${keyword}`} value="default" label={keyword} />)
                    ) : (
                      <span className="text-sm text-muted-foreground">暂无</span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="align-top text-muted-foreground">{formatDate(event.event_date)}</TableCell>
                <TableCell className="align-top">
                  <div className="flex flex-col items-end gap-2">
                    {onParseEvent ? (
                      <Button
                        variant="outline"
                        className="h-8 px-3 text-xs"
                        disabled={busy || parsingEventId === event.id}
                        onClick={() => onParseEvent(event)}
                      >
                        {parseLabel}
                      </Button>
                    ) : null}
                    {event.source_url ? (
                      <Button
                        variant="ghost"
                        className="h-auto px-0 py-0 text-xs text-primary hover:bg-transparent"
                        onClick={() => window.open(event.source_url ?? undefined, "_blank", "noopener,noreferrer")}
                      >
                        查看
                      </Button>
                    ) : (
                      <span className="text-sm text-muted-foreground">暂无链接</span>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
