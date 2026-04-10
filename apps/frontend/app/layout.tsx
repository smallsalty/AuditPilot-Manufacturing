import type { Metadata } from "next";
import { Suspense } from "react";

import { AppShell } from "@/components/app-shell";
import { EnterpriseProvider } from "@/components/enterprise-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "AuditPilot Manufacturing",
  description: "制造业上市公司智能风险识别与审计重点提示系统",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <Suspense fallback={null}>
          <EnterpriseProvider>
            <AppShell>{children}</AppShell>
          </EnterpriseProvider>
        </Suspense>
      </body>
    </html>
  );
}
