"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bot, ClipboardList, FileText, LayoutDashboard, ShieldCheck } from "lucide-react";

import { EnterpriseSwitcher } from "@/components/enterprise-switcher";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "总览", icon: LayoutDashboard },
  { href: "/risks", label: "风险清单", icon: ShieldCheck },
  { href: "/audit-focus", label: "审计重点", icon: ClipboardList },
  { href: "/documents", label: "文档中心", icon: FileText },
  { href: "/chat", label: "AI问答", icon: Bot },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-[#09111f] text-white">
      <div className="mx-auto grid min-h-screen max-w-[1600px] gap-6 px-4 py-4 lg:grid-cols-[300px_minmax(0,1fr)] lg:px-6">
        <aside className="flex flex-col gap-6 rounded-[32px] border border-white/10 bg-slate/85 p-5 shadow-soft backdrop-blur-sm">
          <div className="space-y-3">
            <div>
              <p className="text-xs uppercase tracking-[0.32em] text-steel">AuditPilot</p>
              <h1 className="mt-3 text-2xl font-semibold text-white">制造业审计风险工作台</h1>
            </div>
            <p className="text-sm leading-6 text-haze/70">
              基于企业主数据、官方公告、风险规则和证据链，为制造业上市公司提供风险识别与审计重点提示。
            </p>
          </div>

          <EnterpriseSwitcher />

          <nav className="space-y-2">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const active =
                item.href === "/"
                  ? pathname === item.href
                  : pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm transition",
                    active
                      ? "border-amber-400/30 bg-amber-400/10 text-white"
                      : "border-transparent bg-white/5 text-haze/80 hover:border-white/10 hover:bg-white/10",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          <div className="mt-auto rounded-3xl border border-white/10 bg-white/5 p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-steel">数据说明</p>
            <div className="mt-3 space-y-2 text-sm text-haze/75">
              <p>企业主数据来源：AkShare</p>
              <p>公告与处罚来源：巨潮资讯</p>
              <p>上传文档可参与解析、问答和证据展示。</p>
            </div>
          </div>
        </aside>

        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}
