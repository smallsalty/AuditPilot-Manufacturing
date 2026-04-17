"use client";

import { Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export function DocumentsToolbar({
  enterpriseName,
  currentEnterpriseId,
  officialDocCount,
  message,
  uploadOpen,
  onUploadOpenChange,
  fileName,
  onFileChange,
  onRefresh,
  onUpload,
  disabled,
  uploadDisabled,
}: {
  enterpriseName?: string | null;
  currentEnterpriseId: number | null;
  officialDocCount: number;
  message: string;
  uploadOpen: boolean;
  onUploadOpenChange: (open: boolean) => void;
  fileName: string | null;
  onFileChange: (file: File | null) => void;
  onRefresh: () => void;
  onUpload: () => void;
  disabled: boolean;
  uploadDisabled: boolean;
}) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div className="space-y-2">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">文档中心</p>
          <h2 className="mt-3 text-3xl font-semibold text-foreground">
            {enterpriseName ? `${enterpriseName} 文档中心` : "文档中心"}
          </h2>
        </div>
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">{message}</p>
        {currentEnterpriseId ? (
          <p className="text-sm text-muted-foreground">
            企业 ID：{currentEnterpriseId} | 官方文档 {officialDocCount} 份
          </p>
        ) : null}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Button variant="outline" onClick={onRefresh} disabled={disabled}>
          刷新文档
        </Button>
        <Dialog open={uploadOpen} onOpenChange={onUploadOpenChange}>
          <DialogTrigger asChild>
            <Button disabled={disabled}>
              <Upload className="mr-2 h-4 w-4" />
              上传文档
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>上传企业文档</DialogTitle>
              <DialogDescription>支持 PDF 或文本文件。上传后仍需手动执行解析。</DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <Input
                type="file"
                accept=".pdf,.txt"
                onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
              />
              <p className="text-sm text-muted-foreground">
                {fileName ? `已选择：${fileName}` : "尚未选择文件"}
              </p>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => onUploadOpenChange(false)}>
                取消
              </Button>
              <Button onClick={onUpload} disabled={uploadDisabled}>
                开始上传
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
