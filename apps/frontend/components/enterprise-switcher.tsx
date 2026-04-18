"use client";

import { useEffect, useMemo, useState } from "react";
import { Building2, RefreshCw, Search } from "lucide-react";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function EnterpriseSwitcher() {
  const {
    currentEnterpriseId,
    enterpriseOptions,
    enterpriseLoading,
    enterpriseError,
    refreshEnterpriseOptions,
    searchKeyword,
    selectEnterprise,
    setSearchKeyword,
    bootstrapEnterprise,
  } = useEnterpriseContext();

  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [bootstrapping, setBootstrapping] = useState(false);

  const reloadEnterprises = async () => {
    setSearching(true);
    setSearchError(null);
    try {
      await refreshEnterpriseOptions(searchKeyword.trim(), { force: true });
    } catch (error) {
      setSearchError(error instanceof Error ? error.message : "企业搜索失败。");
    } finally {
      setSearching(false);
    }
  };

  const bootstrap = async () => {
    const query = searchKeyword.trim();
    if (!query) {
      return;
    }
    setBootstrapping(true);
    setSearchError(null);
    try {
      const payload = /^\d{6}(\.(SH|SZ))?$/i.test(query) ? { ticker: query } : { name: query };
      await bootstrapEnterprise(payload);
      setSearchKeyword("");
    } catch (error) {
      setSearchError(error instanceof Error ? error.message : "企业引入失败。");
    } finally {
      setBootstrapping(false);
    }
  };

  useEffect(() => {
    const normalized = searchKeyword.trim();
    if (!normalized) {
      setSearching(false);
      setSearchError(null);
      void refreshEnterpriseOptions("");
      return;
    }

    const timer = window.setTimeout(async () => {
      setSearching(true);
      setSearchError(null);
      try {
        await refreshEnterpriseOptions(normalized);
      } catch (error) {
        setSearchError(error instanceof Error ? error.message : "企业搜索失败。");
      } finally {
        setSearching(false);
      }
    }, 250);

    return () => window.clearTimeout(timer);
  }, [refreshEnterpriseOptions, searchKeyword]);

  const helperText = useMemo(() => {
    if (enterpriseError) return enterpriseError;
    if (searchError) return searchError;
    if (enterpriseLoading) return "正在加载企业列表...";
    if (searching) return "正在搜索企业...";
    if (enterpriseOptions.length === 0 && searchKeyword.trim()) return "未找到匹配企业，可直接引入官方企业。";
    return "支持按企业名称或股票代码搜索。";
  }, [enterpriseError, enterpriseLoading, enterpriseOptions.length, searchError, searching, searchKeyword]);

  return (
    <div className="rounded-xl border bg-background p-4">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-muted p-2 text-muted-foreground">
          <Building2 className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">企业上下文</p>
          <p className="mt-1 text-sm text-muted-foreground">按企业名称或股票代码切换当前工作对象。</p>
        </div>
      </div>

      <div className="relative mt-4">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={searchKeyword}
          onChange={(event) => setSearchKeyword(event.target.value)}
          placeholder="搜索企业名称或股票代码"
          className="pl-10"
        />
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Button
          variant="outline"
          onClick={reloadEnterprises}
          disabled={enterpriseLoading || searching}
          className="min-w-[9rem] whitespace-nowrap"
        >
          <RefreshCw className="mr-2 h-4 w-4" />
          刷新企业列表
        </Button>
        {searchKeyword.trim() ? (
          <Button onClick={bootstrap} disabled={bootstrapping} className="min-w-[9rem] whitespace-nowrap">
            {bootstrapping ? "引入中..." : "引入官方企业"}
          </Button>
        ) : null}
      </div>

      {enterpriseOptions.length > 0 ? (
        <div className="mt-3">
          <Select value={currentEnterpriseId ? String(currentEnterpriseId) : undefined} onValueChange={(value) => selectEnterprise(Number(value))}>
            <SelectTrigger>
              <SelectValue placeholder="请选择企业" />
            </SelectTrigger>
            <SelectContent>
              {enterpriseOptions.map((enterprise) => (
                <SelectItem key={enterprise.id} value={String(enterprise.id)}>
                  {enterprise.name} | {enterprise.ticker}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : (
        <div className="mt-3 rounded-lg border border-dashed bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          暂无可选企业
        </div>
      )}

      <Alert
        variant={enterpriseError || searchError ? "destructive" : "default"}
        className="mt-3 border-dashed bg-muted/30 text-xs"
      >
        <AlertTitle>当前状态</AlertTitle>
        <AlertDescription>{helperText}</AlertDescription>
      </Alert>
    </div>
  );
}
