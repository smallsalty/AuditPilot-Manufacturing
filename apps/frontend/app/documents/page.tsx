"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";

type UploadResult = { id: number; document_name: string; parse_status: string };

export default function DocumentsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [extracts, setExtracts] = useState<{ id: number; title: string; extract_type: string; content: string }[]>([]);
  const [message, setMessage] = useState("可以上传 PDF 或文本文件进行解析。");

  const upload = async () => {
    if (!file) return;
    try {
      const result = (await api.uploadDocument(1, file)) as UploadResult;
      setUploadResult(result);
      setMessage(`文档 ${result.document_name} 上传成功，接下来可执行解析。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "上传失败");
    }
  };

  const parse = async () => {
    if (!uploadResult) return;
    await api.parseDocument(uploadResult.id);
    const response = (await api.getDocumentExtracts(uploadResult.id)) as {
      extracts: { id: number; title: string; extract_type: string; content: string }[];
    };
    setExtracts(response.extracts);
    setMessage(`已抽取 ${response.extracts.length} 条风险相关段落。`);
  };

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-steel">Document Center</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">文档中心</h2>
        <p className="mt-2 text-haze/75">{message}</p>
        <div className="mt-5 flex flex-col gap-3 lg:flex-row">
          <input
            type="file"
            accept=".pdf,.txt"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-haze/75"
          />
          <Button onClick={upload}>上传文档</Button>
          <Button variant="outline" onClick={parse} disabled={!uploadResult}>
            解析并抽取
          </Button>
        </div>
      </Card>
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-steel">Extract Results</p>
        <div className="mt-4 space-y-3">
          {extracts.map((extract) => (
            <div key={extract.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="font-medium text-white">{extract.title}</p>
              <p className="mt-1 text-xs uppercase tracking-[0.2em] text-steel">{extract.extract_type}</p>
              <p className="mt-3 text-haze/80">{extract.content}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

