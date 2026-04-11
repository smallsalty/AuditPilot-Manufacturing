"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Building2, ClipboardList, FileText, MessageSquare, ShieldAlert } from "lucide-react";

import { EnterpriseSwitcher } from "@/components/enterprise-switcher";
import { useEnterpriseContext } from "@/components/enterprise-provider";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: BarChart3 },
  { href: "/risks", label: "风险清单", icon: ShieldAlert },
  { href: "/audit-focus", label: "审计重点", icon: ClipboardList },
  { href: "/documents", label: "文档中心", icon: FileText },
  { href: "/chat", label: "AI问答", icon: MessageSquare },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { currentEnterprise, currentEnterpriseId, enterpriseLoading } = useEnterpriseContext();

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(217,119,6,0.22),_transparent_30%),radial-gradient(circle_at_top_right,_rgba(16,185,129,0.15),_transparent_28%),linear-gradient(180deg,_#09111f_0%,_#0f172a_55%,_#111827_100%)] text-white">
      <div className="mx-auto flex min-h-screen max-w-[1600px] gap-6 px-5 py-6 lg:px-8">
        <aside className="hidden w-72 shrink-0 rounded-[32px] border border-white/10 bg-slate/70 p-5 shadow-soft backdrop-blur md:block">
          <div className="mb-8 flex items-center gap-3">
            <div className="rounded-2xl bg-ember/15 p-3 text-ember">
              <Building2 className="h-6 w-6" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.32em] text-steel">AuditPilot</p>
              <h1 className="text-xl font-semibold text-white">Manufacturing</h1>
            </div>
          </div>

          <nav className="space-y-2">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm transition",
                    active ? "bg-white/10 text-white" : "text-haze/75 hover:bg-white/5 hover:text-white",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="mt-6">
            <EnterpriseSwitcher />
          </div>

          <div className="mt-6 rounded-3xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
            <p className="mb-2 text-xs uppercase tracking-[0.24em] text-steel">Current Enterprise</p>
            {enterpriseLoading ? (
              <p>Initializing enterprise context...</p>
            ) : currentEnterprise ? (
              <>
                <p className="font-medium text-white">{currentEnterprise.name}</p>
                <p className="mt-1 text-haze/75">
                  {currentEnterprise.ticker} | {currentEnterprise.industry_tag}
                </p>
                <p className="mt-2 text-xs text-steel">Enterprise ID: {currentEnterpriseId}</p>
                <Link
                  href={`/enterprises/${currentEnterpriseId}`}
                  className="mt-3 inline-flex text-xs text-amber-300 transition hover:text-amber-200"
                >
                  View audit overview
                </Link>
              </>
            ) : (
              <p>No enterprise is available. Seed or sync data first.</p>
            )}
          </div>

          <div className="mt-8 rounded-3xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
            <p className="mb-2 text-xs uppercase tracking-[0.24em] text-steel">Demo Flow</p>
            <p>Sync source data, run risk analysis, inspect audit focus, and continue with AI Q&A.</p>
          </div>
        </aside>

        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
