"use client";

import type { EnterpriseEventItem } from "@auditpilot/shared-types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatEventType, formatSeverity } from "@/lib/display-labels";

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

export function AnnouncementRawEventsTable({
  events,
  activeEventId,
  activeFallbackKey,
}: {
  events: EnterpriseEventItem[];
  activeEventId: number | null;
  activeFallbackKey: string | null;
}) {
  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-[34%]">标题</TableHead>
            <TableHead>事件类型</TableHead>
            <TableHead>严重程度</TableHead>
            <TableHead>主命中类别</TableHead>
            <TableHead>命中关键词</TableHead>
            <TableHead>日期</TableHead>
            <TableHead className="text-right">链接</TableHead>
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
            const auditFocus = previewList(analysis?.audit_focus);
            return (
              <TableRow key={event.id} className={isActive ? "bg-primary/5" : undefined}>
                <TableCell className="align-top">
                  <div className="space-y-2">
                    <p className="font-medium text-foreground">{event.title}</p>
                    <p className="text-xs text-muted-foreground">{event.summary}</p>
                    {analysis ? (
                      <div className="space-y-1 rounded-lg border bg-muted/30 p-2 text-xs text-muted-foreground">
                        <div className="flex items-center gap-2">
                          <Badge value="default" label="正文分析" />
                          {event.event_analysis_status === "fallback" ? <span>降级结果</span> : null}
                        </div>
                        {analysis.summary && analysis.summary !== event.summary ? (
                          <p className="text-foreground">{analysis.summary}</p>
                        ) : null}
                        {keyFacts.length > 0 ? <p>关键事实：{keyFacts.join("；")}</p> : null}
                        {riskPoints.length > 0 ? <p>风险点：{riskPoints.join("；")}</p> : null}
                        {auditFocus.length > 0 ? <p>审计关注：{auditFocus.join("；")}</p> : null}
                        {analysis.evidence_excerpt ? <p>证据摘录：{analysis.evidence_excerpt}</p> : null}
                      </div>
                    ) : null}
                  </div>
                </TableCell>
                <TableCell className="align-top text-muted-foreground">{formatEventType(event.event_type)}</TableCell>
                <TableCell className="align-top">
                  <Badge value={event.severity.toUpperCase()} label={formatSeverity(event.severity)} />
                </TableCell>
                <TableCell className="align-top text-muted-foreground">{primaryMatch?.category_name ?? "暂无"}</TableCell>
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
                <TableCell className="align-top text-right">
                  {event.source_url ? (
                    <Button
                      variant="ghost"
                      className="h-auto px-0 py-0 text-xs text-primary hover:bg-transparent"
                      onClick={() => window.open(event.source_url ?? undefined, "_blank", "noopener,noreferrer")}
                    >
                      查看
                    </Button>
                  ) : (
                    <span className="text-sm text-muted-foreground">暂无</span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
