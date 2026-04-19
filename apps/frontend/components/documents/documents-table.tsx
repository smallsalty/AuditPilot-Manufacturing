"use client";

import { useState } from "react";
import type { DocumentListItem } from "@auditpilot/shared-types";

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
  onOpenOriginal,
  onDelete,
}: {
  documents: DocumentListItem[];
  activeDocumentId: number | null;
  busy: boolean;
  onView: (document: DocumentListItem) => void;
  onParse: (document: DocumentListItem) => void;
  onOpenOriginal: (document: DocumentListItem) => void;
  onDelete: (document: DocumentListItem) => void;
}) {
  const [deleteTarget, setDeleteTarget] = useState<DocumentListItem | null>(null);

  return (
    <>
      <div className="rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[32%]">文档</TableHead>
              <TableHead className="w-[24%]">操作</TableHead>
              <TableHead>分类</TableHead>
              <TableHead>解析状态</TableHead>
              <TableHead>分析状态</TableHead>
              <TableHead>更新时间</TableHead>
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
                  <TableCell className="align-top">
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        onClick={() => onView(document)}
                        disabled={busy}
                        className="h-8 whitespace-nowrap px-3"
                      >
                        查看抽取
                      </Button>
                      <Button
                        onClick={() => onParse(document)}
                        disabled={busy || document.parse_status === "parsing"}
                        className="h-8 whitespace-nowrap px-3"
                      >
                        {document.parse_status === "parsed" ? "重新解析" : "解析"}
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => onOpenOriginal(document)}
                        disabled={busy}
                        className="h-8 whitespace-nowrap px-3"
                      >
                        查看原文件
                      </Button>
                      <Button
                        variant="destructive"
                        onClick={() => setDeleteTarget(document)}
                        disabled={busy}
                        className="h-8 whitespace-nowrap px-3"
                      >
                        删除
                      </Button>
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
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <Dialog open={Boolean(deleteTarget)} onOpenChange={(open) => (!open ? setDeleteTarget(null) : undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除文档</DialogTitle>
            <DialogDescription>
              确认删除“{deleteTarget?.document_name}”？该操作会删除文档记录、抽取结果和本地原文件，无法撤销。
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
                  onDelete(deleteTarget);
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
