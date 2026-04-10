"use client";

import { useEffect, useMemo, useState } from "react";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useDashboardResource, useDocumentsResource } from "@/lib/enterprise-resources";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: { title: string; content: string; source_type: string }[];
  suggested_actions?: string[];
};

const SUGGESTED_QUESTIONS = [
  "这家公司最值得关注的三个风险是什么？",
  "为什么系统判定存货风险高？",
  "建议执行哪些审计程序？",
];

export default function ChatPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError } = useEnterpriseContext();
  const { data: dashboard, loading: dashboardLoading, error: dashboardError } = useDashboardResource(currentEnterpriseId);
  const { data: documents, loading: docsLoading } = useDocumentsResource(currentEnterpriseId);
  const [question, setQuestion] = useState(SUGGESTED_QUESTIONS[1]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  useEffect(() => {
    setMessages([]);
    setChatError(null);
  }, [currentEnterpriseId]);

  const knowledgeState = useMemo(() => {
    if (!currentEnterpriseId) {
      return { status: "invalid", message: "请重新选择企业。" };
    }
    const analysisStatus = dashboard?.analysis_status ?? "not_started";
    if (analysisStatus === "not_started") {
      return { status: "not_started", message: "当前企业尚未运行风险分析，请先执行分析。" };
    }
    if (analysisStatus === "failed") {
      return { status: "failed", message: dashboard?.last_error ?? "当前企业最近一次分析失败，请重试。" };
    }
    if ((documents?.length ?? 0) === 0) {
      return {
        status: "structured_only",
        message: "当前仅可基于结构化风险结果问答，建议上传年报/公告/PDF 以增强引用依据。",
      };
    }
    return { status: "ready", message: "回答会引用规则摘要、文档片段与已识别风险作为依据。" };
  }, [currentEnterpriseId, dashboard, documents]);

  const send = async (preset?: string) => {
    if (!currentEnterpriseId || loading) return;
    const currentQuestion = preset ?? question;
    if (!currentQuestion.trim()) return;
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
          citations: response.citations,
          suggested_actions: response.suggested_actions,
        },
      ]);
      setQuestion("");
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "问答生成失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-steel">Audit Copilot</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">
          {currentEnterprise ? `${currentEnterprise.name} AI 审计问答` : "AI 审计问答"}
        </h2>
        <p className="mt-2 text-haze/75">
          {enterpriseError
            ? `企业列表加载失败：${enterpriseError}`
            : dashboardLoading || docsLoading
              ? "正在初始化问答上下文..."
              : dashboardError
                ? `总览数据加载失败：${dashboardError}`
                : knowledgeState.message}
        </p>
        {!enterpriseError && currentEnterpriseId && knowledgeState.status !== "not_started" && knowledgeState.status !== "failed" && knowledgeState.status !== "invalid" ? (
          <div className="mt-5 flex flex-wrap gap-3">
            {SUGGESTED_QUESTIONS.map((item) => (
              <button
                key={item}
                onClick={() => send(item)}
                className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-haze/85 transition hover:bg-white/10"
              >
                {item}
              </button>
            ))}
          </div>
        ) : null}
      </Card>

      {knowledgeState.status === "invalid" || knowledgeState.status === "not_started" || knowledgeState.status === "failed" ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">{knowledgeState.message}</div>
        </Card>
      ) : (
        <Card>
          <div className="space-y-4">
            {messages.length > 0 ? (
              messages.map((message, index) => (
                <div
                  key={`${message.role}-${index}`}
                  className={message.role === "user" ? "ml-auto max-w-3xl" : "max-w-4xl"}
                >
                  <div
                    className={
                      message.role === "user"
                        ? "rounded-[24px] bg-ember px-5 py-4 text-white"
                        : "rounded-[24px] border border-white/10 bg-white/5 px-5 py-4 text-haze/85"
                    }
                  >
                    {message.content}
                  </div>
                  {message.citations && (
                    <div className="mt-3 space-y-2">
                      {message.citations.map((citation) => (
                        <div key={`${citation.title}-${citation.source_type}`} className="rounded-2xl border border-white/10 bg-black/10 p-4 text-sm text-haze/75">
                          <p className="font-medium text-white">{citation.title}</p>
                          <p className="mt-2">{citation.content}</p>
                          <p className="mt-2 text-xs uppercase tracking-[0.2em] text-steel">{citation.source_type}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  {message.suggested_actions && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {message.suggested_actions.map((action) => (
                        <span key={action} className="rounded-full bg-white/5 px-3 py-1 text-xs text-haze/80">
                          {action}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
                当前还没有问答记录，可直接点击推荐问题或输入自定义问题。
              </div>
            )}
          </div>
          {chatError ? (
            <div className="mt-4 rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">{chatError}</div>
          ) : null}
          <div className="mt-6 flex flex-col gap-3 lg:flex-row">
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={3}
              placeholder="请输入问题，例如：为什么判定收入确认风险高？"
              className="flex-1 rounded-3xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-amber-400/50"
            />
            <Button
              onClick={() => send()}
              disabled={loading || !currentEnterpriseId || knowledgeState.status === "invalid" || knowledgeState.status === "not_started" || knowledgeState.status === "failed"}
              className="h-fit lg:self-end"
            >
              {loading ? "生成中..." : "发送问题"}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
