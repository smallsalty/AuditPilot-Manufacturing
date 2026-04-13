"use client";

import { useEffect, useMemo, useState } from "react";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useDashboardResource, useDocumentsResource, useReadinessResource } from "@/lib/enterprise-resources";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  basisLevel?: string;
  citations?: { title: string; content: string; source_type: string }[];
  suggested_actions?: string[];
};

const SUGGESTED_QUESTIONS = [
  "这家公司最值得关注的三个风险是什么？",
  "为什么系统判定存货风险较高？",
  "建议优先执行哪些审计程序？",
];

const BASIS_LEVEL_LABELS: Record<string, string> = {
  official_document: "依据等级：官方文档",
  structured_result: "依据等级：结构化结果",
  insufficient_context: "依据等级：信息不足",
};

export default function ChatPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError } = useEnterpriseContext();
  const { data: readiness, loading: readinessLoading, error: readinessError } = useReadinessResource(currentEnterpriseId);
  const { data: dashboard, loading: dashboardLoading } = useDashboardResource(currentEnterpriseId);
  const { data: documents, loading: documentsLoading } = useDocumentsResource(currentEnterpriseId);

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  useEffect(() => {
    setMessages([]);
    setQuestion("");
    setChatError(null);
  }, [currentEnterpriseId]);

  const pageState = useMemo(() => {
    if (enterpriseError) {
      return { kind: "error", message: `企业列表加载失败：${enterpriseError}` };
    }
    if (!currentEnterpriseId || !currentEnterprise) {
      return { kind: "empty", message: "请先选择企业。" };
    }
    if (readinessLoading || dashboardLoading || documentsLoading) {
      return { kind: "loading", message: "正在初始化问答上下文..." };
    }
    if (readinessError) {
      return { kind: "error", message: `问答状态加载失败：${readinessError}` };
    }
    if (!readiness?.profile_ready) {
      return { kind: "empty", message: "当前企业主数据尚未就绪，请先同步源数据。" };
    }
    if (readiness.risk_analysis_status === "running") {
      return { kind: "waiting", message: "风险分析正在执行中，完成后即可基于结果问答。" };
    }
    if (readiness.risk_analysis_status === "failed") {
      return { kind: "error", message: dashboard?.last_error ?? "最近一次风险分析失败，请先重新运行分析。" };
    }
    if (readiness.risk_analysis_status !== "completed") {
      return { kind: "empty", message: "当前企业尚未完成风险分析，请先运行风险分析。" };
    }
    if ((documents?.length ?? 0) === 0) {
      return {
        kind: "structured_only",
        message: "当前仅可基于结构化风险结果问答。若需要官方文档证据，请先同步巨潮或上传文档。",
      };
    }
    return {
      kind: "ready",
      message: "问答将优先引用官方文档、监管公告和结构化风险结果。",
    };
  }, [
    currentEnterprise,
    currentEnterpriseId,
    dashboard?.last_error,
    dashboardLoading,
    documents,
    documentsLoading,
    enterpriseError,
    readiness,
    readinessError,
    readinessLoading,
  ]);

  const send = async (preset?: string) => {
    if (!currentEnterpriseId || loading || (pageState.kind !== "ready" && pageState.kind !== "structured_only")) {
      return;
    }
    const currentQuestion = (preset ?? question).trim();
    if (!currentQuestion) {
      return;
    }
    setLoading(true);
    setChatError(null);
    setMessages((prev) => [...prev, { role: "user", content: currentQuestion }]);
    try {
      const response = await api.chat(currentEnterpriseId, currentQuestion);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.answer,
          basisLevel: response.basis_level,
          citations: response.citations,
          suggested_actions: response.suggested_actions,
        },
      ]);
      setQuestion("");
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "问答生成失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-steel">智能问答</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">
          {currentEnterprise ? `${currentEnterprise.name} 风险问答` : "风险问答"}
        </h2>
        <p className="mt-2 text-haze/75">{pageState.message}</p>
        {currentEnterprise ? (
          <p className="mt-3 text-sm text-haze/65">
            企业代码：{currentEnterprise.ticker} | 官方文档 {readiness?.official_doc_count ?? 0} 份
          </p>
        ) : null}
        {(pageState.kind === "ready" || pageState.kind === "structured_only") && (
          <div className="mt-5 flex flex-wrap gap-3">
            {SUGGESTED_QUESTIONS.map((item) => (
              <button
                key={item}
                onClick={() => void send(item)}
                className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-haze/85 transition hover:bg-white/10"
              >
                {item}
              </button>
            ))}
          </div>
        )}
      </Card>

      {pageState.kind === "loading" || pageState.kind === "empty" || pageState.kind === "waiting" ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">{pageState.message}</div>
        </Card>
      ) : pageState.kind === "error" ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">{pageState.message}</div>
        </Card>
      ) : (
        <Card>
          <div className="space-y-4">
            {messages.length > 0 ? (
              messages.map((message, index) => (
                <div key={`${message.role}-${index}`} className={message.role === "user" ? "ml-auto max-w-3xl" : "max-w-4xl"}>
                  <div
                    className={
                      message.role === "user"
                        ? "rounded-[24px] bg-ember px-5 py-4 text-white"
                        : "rounded-[24px] border border-white/10 bg-white/5 px-5 py-4 text-haze/85"
                    }
                  >
                    {message.content}
                  </div>
                  {message.role === "assistant" && message.basisLevel ? (
                    <p className="mt-2 text-xs uppercase tracking-[0.18em] text-steel">
                      {BASIS_LEVEL_LABELS[message.basisLevel] ?? `依据等级：${message.basisLevel}`}
                    </p>
                  ) : null}
                  {message.citations?.length ? (
                    <div className="mt-3 space-y-2">
                      {message.citations.map((citation, citationIndex) => (
                        <div
                          key={`${citation.title}-${citation.source_type}-${citationIndex}`}
                          className="rounded-2xl border border-white/10 bg-black/10 p-4 text-sm text-haze/75"
                        >
                          <p className="font-medium text-white">{citation.title}</p>
                          <p className="mt-2">{citation.content}</p>
                          <p className="mt-2 text-xs uppercase tracking-[0.2em] text-steel">{citation.source_type}</p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {message.suggested_actions?.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {message.suggested_actions.map((action) => (
                        <span key={action} className="rounded-full bg-white/5 px-3 py-1 text-xs text-haze/80">
                          {action}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
                当前还没有问答记录。可以直接点击推荐问题，或输入自定义问题。
              </div>
            )}
          </div>

          {chatError ? (
            <div className="mt-4 rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
              {chatError}
            </div>
          ) : null}

          <div className="mt-6 flex flex-col gap-3 lg:flex-row">
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={3}
              placeholder="请输入问题，例如：为什么判定收入确认风险较高？"
              className="flex-1 rounded-3xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-amber-400/50"
            />
            <Button onClick={() => void send()} disabled={loading || pageState.kind === "error"} className="h-fit lg:self-end">
              {loading ? "生成中..." : "发送问题"}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
