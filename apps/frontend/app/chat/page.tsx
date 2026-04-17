"use client";

import { useEffect, useMemo, useState } from "react";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatSourceType } from "@/lib/display-labels";
import { useDocumentsResource, useReadinessResource } from "@/lib/enterprise-resources";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  basisLevel?: string;
  citations?: { title: string; content: string; source_type: string }[];
  suggested_actions?: string[];
};

const SUGGESTED_QUESTIONS = [
  "这家公司当前最值得关注的三项审计风险是什么？",
  "文档里哪些披露最需要进一步复核？",
  "下一步应优先执行哪些审计程序？",
];

const BASIS_LEVEL_LABELS: Record<string, string> = {
  official_document: "依据等级：官方文档",
  structured_result: "依据等级：结构化结果",
  insufficient_context: "依据等级：信息不足",
  fallback_context: "依据等级：回退结果",
};

const COLLAPSED_ANSWER_MAX_HEIGHT = 224;
const LONG_ANSWER_THRESHOLD = 320;

export default function ChatPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError } = useEnterpriseContext();
  const { data: readiness, loading: readinessLoading, error: readinessError } = useReadinessResource(currentEnterpriseId);
  const { data: documents, loading: documentsLoading } = useDocumentsResource(currentEnterpriseId);

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [expandedMessages, setExpandedMessages] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  useEffect(() => {
    setMessages([]);
    setExpandedMessages({});
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
    if (readinessLoading || documentsLoading) {
      return { kind: "loading", message: "正在初始化问答上下文..." };
    }
    if (readinessError) {
      return { kind: "error", message: `问答状态加载失败：${readinessError}` };
    }
    if (!readiness?.profile_ready) {
      return { kind: "empty", message: "当前企业主数据尚未就绪，请先同步源数据。" };
    }
    if ((documents?.length ?? 0) === 0 && !readiness.qa_ready) {
      return { kind: "empty", message: "当前企业还没有可用于问答的文档或风险依据。" };
    }
    return { kind: "ready", message: "问答将优先引用官方文档抽取、文档风险和结构化风险结果。" };
  }, [currentEnterprise, currentEnterpriseId, documents, documentsLoading, enterpriseError, readiness, readinessError, readinessLoading]);

  const send = async (preset?: string) => {
    if (!currentEnterpriseId || loading || pageState.kind !== "ready") {
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
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">智能问答</p>
        <h2 className="mt-3 text-3xl font-semibold text-foreground">
          {currentEnterprise ? `${currentEnterprise.name} 风险问答` : "风险问答"}
        </h2>
        <p className="mt-2 text-muted-foreground">{pageState.message}</p>
        {currentEnterprise ? (
          <p className="mt-3 text-sm text-muted-foreground">
            企业代码：{currentEnterprise.ticker} | 官方文档 {readiness?.official_doc_count ?? 0} 份
          </p>
        ) : null}
        {pageState.kind === "ready" && (
          <div className="mt-5 flex flex-wrap gap-3">
            {SUGGESTED_QUESTIONS.map((item) => (
              <button
                key={item}
                onClick={() => void send(item)}
                className="rounded-full border border-border bg-muted/30 px-4 py-2 text-sm text-muted-foreground transition hover:bg-muted"
              >
                {item}
              </button>
            ))}
          </div>
        )}
      </Card>

      {pageState.kind === "loading" || pageState.kind === "empty" ? (
        <Card>
          <div className="rounded-xl border border-dashed bg-muted/30 p-5 text-sm text-muted-foreground">{pageState.message}</div>
        </Card>
      ) : pageState.kind === "error" ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">{pageState.message}</div>
        </Card>
      ) : (
        <Card>
          <div className="space-y-4">
            {messages.length > 0 ? (
              messages.map((message, index) => {
                const messageKey = `${message.role}-${index}`;
                const isLongAssistantMessage =
                  message.role === "assistant" && message.content.trim().length > LONG_ANSWER_THRESHOLD;
                const expanded = expandedMessages[messageKey] ?? false;

                return (
                  <div key={messageKey} className={message.role === "user" ? "ml-auto max-w-3xl" : "max-w-4xl"}>
                    <div
                      className={
                        message.role === "user"
                          ? "rounded-[24px] bg-primary px-5 py-4 text-primary-foreground"
                          : "rounded-[24px] border border-border bg-muted/20 px-5 py-4 text-foreground"
                      }
                    >
                      <div
                        className="whitespace-pre-wrap break-words"
                        style={
                          isLongAssistantMessage && !expanded
                            ? { maxHeight: `${COLLAPSED_ANSWER_MAX_HEIGHT}px`, overflow: "hidden" }
                            : undefined
                        }
                      >
                        {message.content}
                      </div>
                      {isLongAssistantMessage ? (
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedMessages((current) => ({
                              ...current,
                              [messageKey]: !expanded,
                            }))
                          }
                          className="mt-3 text-sm text-primary transition hover:text-primary/80"
                        >
                          {expanded ? "收起" : "展开全文"}
                        </button>
                      ) : null}
                    </div>
                    {message.role === "assistant" && message.basisLevel ? (
                      <p className="mt-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        {BASIS_LEVEL_LABELS[message.basisLevel] ?? `依据等级：${message.basisLevel}`}
                      </p>
                    ) : null}
                    {message.citations?.length ? (
                      <div className="mt-3 space-y-2">
                        {message.citations.map((citation, citationIndex) => (
                          <div
                            key={`${citation.title}-${citation.source_type}-${citationIndex}`}
                            className="rounded-xl border border-border bg-muted/30 p-4 text-sm text-muted-foreground"
                          >
                            <p className="font-medium text-foreground">{citation.title}</p>
                            <p className="mt-2">{citation.content}</p>
                            <p className="mt-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">
                              {formatSourceType(citation.source_type)}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    {message.suggested_actions?.length ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {message.suggested_actions.map((action) => (
                          <span key={action} className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
                            {action}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })
            ) : (
              <div className="rounded-xl border border-dashed bg-muted/30 p-5 text-sm text-muted-foreground">
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
              className="flex-1 rounded-xl border border-input bg-background px-4 py-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
            />
            <Button onClick={() => void send()} disabled={loading || pageState.kind !== "ready"} className="h-fit lg:self-end">
              {loading ? "生成中..." : "发送问题"}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
