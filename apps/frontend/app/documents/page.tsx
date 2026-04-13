"use client";

import { useEffect, useMemo, useState } from "react";
import type { DocumentListItem } from "@auditpilot/shared-types";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useDocumentsResource, useReadinessResource } from "@/lib/enterprise-resources";

type ExtractItem = { id: number; title: string; extract_type: string; content: string };

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
  const [extracts, setExtracts] = useState<ExtractItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("支持上传 PDF 或文本文件，并与当前企业的官方文档一并展示。");

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
    if (!file || !currentEnterpriseId) {
      return;
    }
    setBusy(true);
    try {
      const result = await api.uploadDocument(currentEnterpriseId, file);
      invalidateEnterpriseResources(currentEnterpriseId, ["documents", "readiness"]);
      await refresh();
      setActiveDocumentId(result.id);
      setMessage(`文档 ${result.document_name} 上传成功。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "文档上传失败。");
    } finally {
      setBusy(false);
    }
  };

  const parse = async (document: DocumentListItem) => {
    setBusy(true);
    try {
      await api.parseDocument(document.id);
      const response = (await api.getDocumentExtracts(document.id)) as { extracts: ExtractItem[] };
      invalidateEnterpriseResources(currentEnterpriseId ?? 0, ["documents"]);
      await refresh();
      setActiveDocumentId(document.id);
      setExtracts(response.extracts);
      setMessage(`已抽取 ${response.extracts.length} 条文档片段。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "文档解析失败。");
    } finally {
      setBusy(false);
    }
  };

  const loadExtracts = async (document: DocumentListItem) => {
    setBusy(true);
    try {
      const response = (await api.getDocumentExtracts(document.id)) as { extracts: ExtractItem[] };
      setActiveDocumentId(document.id);
      setExtracts(response.extracts);
      setMessage(`已加载 ${document.document_name} 的抽取结果。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "抽取结果加载失败。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-steel">文档中心</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">
          {currentEnterprise ? `${currentEnterprise.name} 文档中心` : "文档中心"}
        </h2>
        <p className="mt-2 text-haze/75">{message}</p>
        {currentEnterprise ? (
          <p className="mt-3 text-sm text-haze/65">当前企业官方文档：{readiness?.official_doc_count ?? 0} 份</p>
        ) : null}
        <div className="mt-5 flex flex-col gap-3 lg:flex-row">
          <input
            type="file"
            accept=".pdf,.txt"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-haze/75"
          />
          <Button onClick={upload} disabled={!file || !currentEnterpriseId || busy}>
            {busy ? "处理中..." : "上传文档"}
          </Button>
        </div>
      </Card>

      {enterpriseError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
            企业列表加载失败：{enterpriseError}
          </div>
        </Card>
      ) : !currentEnterpriseId ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">请先选择企业。</div>
        </Card>
      ) : loading ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">正在加载企业文档列表...</div>
        </Card>
      ) : error ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
            文档列表加载失败：{error}
          </div>
        </Card>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
          <Card>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">文档列表</p>
            {documents && documents.length > 0 ? (
              <div className="mt-4 space-y-3">
                {documents.map((document) => (
                  <div key={document.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                      <div>
                        <p className="font-medium text-white">{document.document_name}</p>
                        <p className="mt-1 text-xs uppercase tracking-[0.2em] text-steel">
                          {document.document_type} | {PARSE_STATUS_LABELS[document.parse_status] ?? document.parse_status} |{" "}
                          {document.source}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <Button variant="outline" onClick={() => void loadExtracts(document)} disabled={busy}>
                          查看抽取
                        </Button>
                        <Button onClick={() => void parse(document)} disabled={busy || document.parse_status === "parsing"}>
                          {document.parse_status === "parsed" ? "重新解析" : "解析"}
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                当前企业暂无文档。可以先同步官方公告，或上传 PDF 与文本文件。
              </div>
            )}
          </Card>

          <Card>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">抽取结果</p>
            {activeDocument ? <p className="mt-2 text-sm text-haze/70">当前文档：{activeDocument.document_name}</p> : null}
            {extracts.length > 0 ? (
              <div className="mt-4 space-y-3">
                {extracts.map((extract) => (
                  <div key={extract.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <p className="font-medium text-white">{extract.title}</p>
                    <p className="mt-1 text-xs uppercase tracking-[0.2em] text-steel">{extract.extract_type}</p>
                    <p className="mt-3 text-haze/80">{extract.content}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                暂无抽取结果。请选择文档查看，或先执行解析。
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
