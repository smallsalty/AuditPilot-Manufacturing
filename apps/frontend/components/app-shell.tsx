"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bot, ClipboardList, FileText, LayoutDashboard, Menu, ShieldCheck } from "lucide-react";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { EnterpriseSwitcher } from "@/components/enterprise-switcher";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "总览", icon: LayoutDashboard },
  { href: "/risks", label: "风险清单", icon: ShieldCheck },
  { href: "/audit-focus", label: "审计重点", icon: ClipboardList },
  { href: "/documents", label: "文档中心", icon: FileText },
  { href: "/chat", label: "AI问答", icon: Bot },
];

const PAGE_META = new Map(
  NAV_ITEMS.map((item) => [
    item.href,
    {
      title: item.label,
      description:
        item.href === "/documents"
          ? "围绕官方文档、手动上传与结构化抽取组织企业文档工作流。"
          : item.href === "/risks"
            ? "查看规则命中、文档证据和风险聚合结果。"
            : item.href === "/audit-focus"
              ? "按证据与风险结果归纳当前审计重点。"
              : item.href === "/chat"
                ? "基于官方文档、风险结果和结构化抽取开展问答。"
                : "查看企业整体风险画像、趋势和数据准备情况。",
    },
  ]),
);

function AppNavigation({ pathname }: { pathname: string }) {
  return (
    <nav className="space-y-1.5">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const active =
          item.href === "/" ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
              active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { currentEnterprise, currentEnterpriseId } = useEnterpriseContext();
  const currentPage =
    PAGE_META.get(pathname) ??
    PAGE_META.get(
      NAV_ITEMS.find((item) => item.href !== "/" && pathname.startsWith(`${item.href}/`))?.href ?? "/",
    ) ??
    PAGE_META.get("/")!;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto grid min-h-screen max-w-[1680px] lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="hidden border-r bg-card/90 lg:flex lg:flex-col">
          <div className="flex h-full flex-col gap-6 px-6 py-7">
            <div className="space-y-3">
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">AuditPilot</p>
                <h1 className="mt-3 text-2xl font-semibold text-foreground">制造业审计风险工作台</h1>
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                面向上市制造企业的文档、风险与审计判断后台。
              </p>
            </div>

            <EnterpriseSwitcher />

            <div className="space-y-3">
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">主导航</p>
              <AppNavigation pathname={pathname} />
            </div>

            <div className="mt-auto rounded-xl border bg-muted/40 p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">数据范围</p>
              <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                <p>企业主数据：AkShare</p>
                <p>公告来源：巨潮资讯</p>
                <p>上传文档参与解析、风险聚合和问答。</p>
              </div>
            </div>
          </div>
        </aside>

        <div className="min-w-0">
          <header className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur">
            <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-6">
              <div className="flex min-w-0 items-center gap-3">
                <Sheet>
                  <SheetTrigger asChild>
                    <Button variant="outline" className="lg:hidden">
                      <Menu className="h-4 w-4" />
                    </Button>
                  </SheetTrigger>
                  <SheetContent side="left" className="w-[320px] p-0">
                    <div className="flex h-full flex-col gap-6 px-6 py-7">
                      <SheetHeader className="space-y-3">
                        <SheetTitle>制造业审计风险工作台</SheetTitle>
                        <SheetDescription>企业后台导航与企业上下文切换。</SheetDescription>
                      </SheetHeader>
                      <EnterpriseSwitcher />
                      <Separator />
                      <AppNavigation pathname={pathname} />
                    </div>
                  </SheetContent>
                </Sheet>
                <div className="min-w-0">
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">当前模块</p>
                  <h2 className="truncate text-lg font-semibold text-foreground">{currentPage.title}</h2>
                </div>
              </div>
              <div className="hidden min-w-0 flex-1 justify-end md:flex">
                <div className="min-w-0 text-right">
                  <p className="truncate text-sm font-medium text-foreground">
                    {currentEnterprise?.name ?? "尚未选择企业"}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {currentEnterprise
                      ? `${currentEnterprise.ticker} | ${currentEnterprise.industry_tag} | 企业 ID ${currentEnterpriseId}`
                      : currentPage.description}
                  </p>
                </div>
              </div>
            </div>
          </header>

          <main className="min-w-0 px-4 py-6 sm:px-6">
            <div className="mx-auto max-w-[1360px] min-w-0">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
