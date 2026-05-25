"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { BarChart3, Bot, ClipboardList, FileText, LayoutDashboard, Menu, ShieldCheck } from "lucide-react";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { EnterpriseSwitcher } from "@/components/enterprise-switcher";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "总览", icon: LayoutDashboard },
  { href: "/risks", label: "风险分析", icon: ShieldCheck },
  { href: "/audit-focus", label: "审计建议", icon: ClipboardList },
  { href: "/financials", label: "财报数据", icon: BarChart3 },
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
            ? "查看文档、公告、数据和财报汇集后的风险分析。"
            : item.href === "/audit-focus"
              ? "按证据与风险结果归纳当前审计建议。"
              : item.href === "/financials"
                ? "展示 AkShare 与巨潮资讯文档抽取后的结构化财报数据。"
              : item.href === "/chat"
                ? "基于官方文档、风险结果和结构化抽取开展问答。"
                : "查看企业整体风险画像、趋势和数据准备情况。",
    },
  ]),
);

function buildNavHref(href: string, enterpriseId: number | null): string {
  if (!enterpriseId) {
    return href;
  }
  return `${href}${href.includes("?") ? "&" : "?"}enterpriseId=${enterpriseId}`;
}

function parseEnterpriseId(value: string | null): number | null {
  const id = Number(value);
  return Number.isFinite(id) && id > 0 ? id : null;
}

function AppNavigation({
  pathname,
  currentEnterpriseId,
  pendingHref,
  onNavigate,
}: {
  pathname: string;
  currentEnterpriseId: number | null;
  pendingHref: string | null;
  onNavigate: (href: string) => void;
}) {
  return (
    <nav className="space-y-1.5">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const active =
          item.href === "/" ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
        const href = buildNavHref(item.href, currentEnterpriseId);
        const pending = pendingHref === href && !active;
        return (
          <Link
            key={item.href}
            href={href}
            aria-current={active ? "page" : undefined}
            onClick={() => onNavigate(href)}
            className={cn(
              "audit-hover-lift flex items-center gap-3 rounded-full border px-3 py-2.5 text-sm font-bold",
              active
                ? "border-[#15130f] bg-[#15130f] text-[#fffaf0] shadow-[6px_6px_0_rgba(226,76,116,0.18)]"
                : pending
                  ? "border-[#d8c8aa] bg-[#f8f3e8] text-[#15130f] opacity-80 shadow-[3px_3px_0_rgba(216,200,170,0.34)]"
                : "border-transparent text-[#5d503b] hover:border-[#d8c8aa] hover:bg-[#f8f3e8]/85 hover:text-[#15130f]",
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
  const searchParams = useSearchParams();
  const searchParamsKey = searchParams.toString();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const { currentEnterprise, currentEnterpriseId } = useEnterpriseContext();
  const navEnterpriseId = currentEnterpriseId ?? parseEnterpriseId(searchParams.get("enterpriseId"));
  const currentPage =
    PAGE_META.get(pathname) ??
    PAGE_META.get(
      NAV_ITEMS.find((item) => item.href !== "/" && pathname.startsWith(`${item.href}/`))?.href ?? "/",
    ) ??
    PAGE_META.get("/")!;

  useEffect(() => {
    setPendingHref(null);
    setMobileNavOpen(false);
  }, [pathname, searchParamsKey]);

  return (
    <div className="min-h-screen text-[#15130f]">
      <div className="mx-auto grid min-h-screen max-w-[1680px] lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="audit-panel hidden border-r border-[#1d1912]/10 lg:sticky lg:top-0 lg:flex lg:h-screen lg:self-start lg:flex-col">
          <div className="flex h-full min-h-0 flex-col gap-6 overflow-y-auto px-6 py-7">
            <div className="space-y-3">
              <div>
                <p className="audit-label">AuditPilot</p>
                <h1 className="audit-title mt-3 whitespace-nowrap text-xl">制造业审计风险工作台</h1>
              </div>
              <p className="audit-copy text-sm">
                面向上市制造企业的数据、公告，财报，文件的聚合审计分析助手
              </p>
            </div>

            <EnterpriseSwitcher />

            <div className="space-y-3">
              <p className="audit-label">主导航</p>
              <AppNavigation
                pathname={pathname}
                currentEnterpriseId={navEnterpriseId}
                pendingHref={pendingHref}
                onNavigate={setPendingHref}
              />
            </div>

          </div>
        </aside>

        <div className="min-w-0">
          <header className="sticky top-0 z-20 border-b border-[#1d1912]/10 bg-[#fffaf0]/88 backdrop-blur">
            <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-6">
              <div className="flex min-w-0 items-center gap-3">
                <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
                  <Button
                    type="button"
                    variant="outline"
                    className="lg:hidden"
                    onClick={() => setMobileNavOpen(true)}
                  >
                    <Menu className="h-4 w-4" />
                  </Button>
                  <SheetContent side="left" className="w-[320px] p-0">
                    <div className="flex h-full flex-col gap-6 px-6 py-7">
                      <SheetHeader className="space-y-3">
                        <SheetTitle>制造业审计风险工作台</SheetTitle>
                        <SheetDescription>企业后台导航与企业上下文切换。</SheetDescription>
                      </SheetHeader>
                      <EnterpriseSwitcher />
                      <Separator />
                      <AppNavigation
                        pathname={pathname}
                        currentEnterpriseId={navEnterpriseId}
                        pendingHref={pendingHref}
                        onNavigate={setPendingHref}
                      />
                    </div>
                  </SheetContent>
                </Sheet>
                <div className="min-w-0">
                  <p className="audit-label">当前模块</p>
                  <h2 className="audit-title truncate text-lg">{currentPage.title}</h2>
                </div>
              </div>
              <div className="hidden min-w-0 flex-1 justify-end md:flex">
                <div className="min-w-0 text-right">
                  <p className="truncate text-sm font-black text-[#15130f]">
                    {currentEnterprise?.name ?? "尚未选择企业"}
                  </p>
                  <p className="truncate text-xs font-semibold text-[#5d503b]">
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
