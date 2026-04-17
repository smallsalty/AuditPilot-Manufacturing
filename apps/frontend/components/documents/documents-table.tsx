"use client";

import type { DocumentListItem } from "@auditpilot/shared-types";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  formatAnalysisMode,
  formatAnalysisStatus,
  formatDocumentType,
  formatParseStatus,
  formatSourceName,
} from "@/lib/display-labels";

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

export function DocumentsTable({
  documents,
  activeDocumentId,
  busy,
  onView,
  onParse,
}: {
  documents: DocumentListItem[];
  activeDocumentId: number | null;
  busy: boolean;
  onView: (document: DocumentListItem) => void;
  onParse: (document: DocumentListItem) => void;
}) {
  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-[34%]">文档</TableHead>
            <TableHead>分类</TableHead>
            <TableHead>解析状态</TableHead>
            <TableHead>分析状态</TableHead>
            <TableHead>更新时间</TableHead>
            <TableHead className="text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.map((document) => {
            const isActive = document.id === activeDocumentId;
            return (
              <TableRow key={document.id} className={isActive ? "bg-muted/40" : undefined}>
                <TableCell className="align-top">
                  <div className="space-y-2">
                    <div className="font-medium text-foreground">{document.document_name}</div>
                    <div className="text-xs text-muted-foreground">{formatSourceName(document.source)}</div>
                    {document.last_error_message ? (
                      <div className="text-xs text-amber-700">
                        最近错误：{document.last_error_message}
                        {document.last_error_at ? ` | ${formatTimestamp(document.last_error_at)}` : ""}
                      </div>
                    ) : null}
                  </div>
                </TableCell>
                <TableCell className="align-top text-muted-foreground">
                  {formatDocumentType(document.classified_type ?? document.document_type)}
                </TableCell>
                <TableCell className="align-top">
                  <Badge value={document.parse_status} label={formatParseStatus(document.parse_status)} />
                </TableCell>
                <TableCell className="align-top">
                  <div className="space-y-1">
                    <div className="text-sm text-foreground">{formatAnalysisStatus(document.analysis_status)}</div>
                    <div className="text-xs text-muted-foreground">{formatAnalysisMode(document.analysis_mode)}</div>
                  </div>
                </TableCell>
                <TableCell className="align-top text-muted-foreground">
                  {formatTimestamp(document.analyzed_at ?? document.created_at)}
                </TableCell>
                <TableCell className="align-top">
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button variant="outline" onClick={() => onView(document)} disabled={busy}>
                      查看抽取
                    </Button>
                    <Button
                      onClick={() => onParse(document)}
                      disabled={busy || document.parse_status === "parsing"}
                    >
                      {document.parse_status === "parsed" ? "重新解析" : "解析"}
                    </Button>
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
