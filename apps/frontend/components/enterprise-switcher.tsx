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
    <div className="audit-subpanel rounded-2xl border border-[#1d1912]/10 p-4">
      <div className="flex items-start gap-3">
        <div className="rounded-full border border-[#d8c8aa] bg-[#fffdf7] p-2 text-[#8f3148]">
          <Building2 className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <p className="audit-label">企业查询</p>
        </div>
      </div>

      <div className="relative mt-4">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8a7759]" />
        <Input
          value={searchKeyword}
          onChange={(event) => setSearchKeyword(event.target.value)}
          placeholder="搜索企业名称或股票代码"
          className="pl-8 pr-2 text-[12px]"
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
        <div className="mt-3 rounded-xl border border-dashed border-[#d8c8aa] bg-[#f8f3e8]/75 px-4 py-3 text-sm font-semibold text-[#6c5d45]">
          暂无可选企业
        </div>
      )}

      <Alert
        variant={enterpriseError || searchError ? "destructive" : "default"}
        className="mt-3 border-dashed text-xs"
      >
        <AlertTitle>当前状态</AlertTitle>
        <AlertDescription>{helperText}</AlertDescription>
      </Alert>
    </div>
  );
}
