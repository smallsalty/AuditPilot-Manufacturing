"use client";

import { useState } from "react";
import type { EnterpriseEventItem } from "@auditpilot/shared-types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cleanDisplayText } from "@/lib/display-text";
import { formatKnownLabel } from "@/lib/display-labels";

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

const eventActionButtonClass = "h-8 w-[4.75rem] justify-center px-2 text-center text-xs";

export function AnnouncementRawEventsTable({
  events,
  activeEventId,
  activeFallbackKey,
  busy,
  parsingEventId,
  onParseEvent,
  onDeleteEvent,
}: {
  events: EnterpriseEventItem[];
  activeEventId: number | null;
  activeFallbackKey: string | null;
  busy?: boolean;
  parsingEventId?: number | null;
  onParseEvent?: (event: EnterpriseEventItem) => void;
  onDeleteEvent?: (event: EnterpriseEventItem) => void;
}) {
  const [deleteTarget, setDeleteTarget] = useState<EnterpriseEventItem | null>(null);
  const deleteTargetTitle = cleanDisplayText(deleteTarget?.title, "未命名公告事件");

  return (
    <>
      <div className="rounded-2xl border border-[#1d1912]/10">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[34%]">分析链</TableHead>
              <TableHead>风险评分</TableHead>
              <TableHead>主命中事件类别</TableHead>
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
                <TableRow key={event.id} className={isActive ? "bg-[#e24c74]/10" : undefined}>
                  <TableCell className="align-top">
                    <div className="space-y-2">
                      <div className="rounded-xl border border-[#1d1912]/10 bg-[#fffdf7]/85 p-2">
                        <p className="text-xs font-bold text-[#8a7759]">公告名称</p>
                        <p className="mt-1 font-black text-[#15130f]">{displayTitle}</p>
                      </div>
                      <div className="rounded-xl border border-[#1d1912]/10 bg-[#f8f3e8]/70 p-2 text-xs font-semibold text-[#5d503b]">
                        <p className="font-black text-[#15130f]">正文分析</p>
                        {keyFacts.length > 0 ? numberedItems(keyFacts) : <p className="mt-1">待分析</p>}
                        {event.event_analysis_status === "fallback" ? <p className="mt-1">降级结果</p> : null}
                      </div>
                      <div className="rounded-xl border border-[#d6a65e]/35 bg-[#f4dfb9]/45 p-2 text-xs font-semibold text-[#7a4b14]">
                        <p className="font-black">风险点</p>
                        {riskPoints.length > 0 ? numberedItems(riskPoints) : <p className="mt-1">暂无</p>}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="align-top">
                    <Badge value={event.severity.toUpperCase()} label={`${riskScoreFromSeverity(event.severity)}分`} />
                  </TableCell>
                  <TableCell className="align-top text-[#5d503b]">
                    {formatKnownLabel(primaryMatch?.category_name, "暂无")}
                  </TableCell>
                  <TableCell className="align-top">
                    <div className="flex flex-wrap gap-2">
                      {keywords.length > 0 ? (
                        keywords.map((keyword) => <Badge key={`${event.id}-${keyword}`} value="default" label={keyword} />)
                      ) : (
                        <span className="text-sm font-semibold text-[#8a7759]">暂无</span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="align-top text-[#5d503b]">{formatDate(event.event_date)}</TableCell>
                  <TableCell className="align-top">
                    <div className="flex flex-col items-end gap-2">
                      {onParseEvent ? (
                        <Button
                          variant="outline"
                          className={eventActionButtonClass}
                          disabled={busy || parsingEventId === event.id}
                          onClick={() => onParseEvent(event)}
                        >
                          {parseLabel}
                        </Button>
                      ) : null}
                      {event.source_url ? (
                        <Button
                          variant="outline"
                          className={eventActionButtonClass}
                          onClick={() => window.open(event.source_url ?? undefined, "_blank", "noopener,noreferrer")}
                        >
                          查看
                        </Button>
                      ) : (
                        <span className="text-sm font-semibold text-[#8a7759]">暂无链接</span>
                      )}
                      {onDeleteEvent ? (
                        <Button
                          variant="destructive"
                          className={eventActionButtonClass}
                          disabled={busy}
                          onClick={() => setDeleteTarget(event)}
                        >
                          删除
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <Dialog open={Boolean(deleteTarget)} onOpenChange={(open) => (!open ? setDeleteTarget(null) : undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除公告事件</DialogTitle>
            <DialogDescription>
              确认删除“{deleteTargetTitle}”？该操作会删除公告事件记录、正文分析和关联风险结果，无法撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={busy}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (deleteTarget) {
                  onDeleteEvent?.(deleteTarget);
                }
                setDeleteTarget(null);
              }}
              disabled={busy}
            >
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
