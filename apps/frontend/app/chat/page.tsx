"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";

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
  const [question, setQuestion] = useState(SUGGESTED_QUESTIONS[1]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);

  const send = async (preset?: string) => {
    const currentQuestion = preset ?? question;
    if (!currentQuestion.trim()) return;
    setLoading(true);
    setMessages((prev) => [...prev, { role: "user", content: currentQuestion }]);
    try {
      const response = await api.chat(1, currentQuestion);
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
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-steel">Audit Copilot</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">AI 审计问答</h2>
        <p className="mt-2 text-haze/75">回答会引用规则摘要、文档片段与已识别风险作为依据。</p>
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
      </Card>

      <Card>
        <div className="space-y-4">
          {messages.map((message, index) => (
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
          ))}
        </div>
        <div className="mt-6 flex flex-col gap-3 lg:flex-row">
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={3}
            placeholder="请输入问题，例如：为什么判定收入确认风险高？"
            className="flex-1 rounded-3xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-amber-400/50"
          />
          <Button onClick={() => send()} disabled={loading} className="h-fit lg:self-end">
            {loading ? "生成中..." : "发送问题"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
