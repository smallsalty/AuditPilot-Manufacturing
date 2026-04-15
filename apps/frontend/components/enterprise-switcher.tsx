"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw, Search } from "lucide-react";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Button } from "@/components/ui/button";

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
    <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-steel">企业上下文</p>
      <div className="relative mt-4">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel" />
        <input
          value={searchKeyword}
          onChange={(event) => setSearchKeyword(event.target.value)}
          placeholder="搜索企业名称或股票代码"
          className="w-full rounded-2xl border border-white/10 bg-black/10 py-3 pl-10 pr-4 text-sm text-white outline-none transition focus:border-amber-400/50"
        />
      </div>
      <div className="mt-3 grid gap-3">
        <Button variant="outline" onClick={reloadEnterprises} disabled={enterpriseLoading || searching}>
          <RefreshCw className="mr-2 h-4 w-4" />
          刷新企业列表
        </Button>
        {searchKeyword.trim() ? (
          <Button onClick={bootstrap} disabled={bootstrapping}>
            {bootstrapping ? "引入中..." : "引入官方企业"}
          </Button>
        ) : null}
      </div>
      {enterpriseOptions.length > 0 ? (
        <select
          value={currentEnterpriseId ?? ""}
          onChange={(event) => selectEnterprise(Number(event.target.value))}
          className="mt-3 w-full rounded-2xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-white outline-none transition focus:border-amber-400/50"
        >
          {enterpriseOptions.map((enterprise) => (
            <option key={enterprise.id} value={enterprise.id} className="bg-slate text-white">
              {enterprise.name} | {enterprise.ticker}
            </option>
          ))}
        </select>
      ) : (
        <div className="mt-3 rounded-2xl border border-white/10 bg-black/10 px-4 py-3 text-sm text-haze/75">
          暂无可选企业
        </div>
      )}
      <p className="mt-3 text-xs text-haze/65">{helperText}</p>
    </div>
  );
}
