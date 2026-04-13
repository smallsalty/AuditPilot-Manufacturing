"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type {
  AuditFocusPayload,
  DashboardPayload,
  DocumentListItem,
  EnterpriseContextState,
  EnterpriseReadinessPayload,
  EnterpriseSearchItem,
  RiskResultPayload,
} from "@auditpilot/shared-types";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { api } from "@/lib/api";

const ENTERPRISE_STORAGE_KEY = "auditpilot.currentEnterpriseId";
const SEARCH_CACHE_TTL = 30_000;

type ResourceKind = "dashboard" | "riskResults" | "auditFocus" | "documents" | "readiness";

type EnterpriseContextValue = EnterpriseContextState & {
  selectEnterprise: (enterpriseId: number) => void;
  setSearchKeyword: (value: string) => void;
  refreshEnterpriseOptions: (query?: string, options?: { force?: boolean }) => Promise<EnterpriseSearchItem[]>;
  bootstrapEnterprise: (payload: { ticker?: string; name?: string }) => Promise<EnterpriseSearchItem>;
  getCachedResource: <T>(kind: ResourceKind, enterpriseId: number) => T | null;
  setCachedResource: <T>(kind: ResourceKind, enterpriseId: number, value: T) => void;
  invalidateEnterpriseResources: (enterpriseId: number, kinds?: ResourceKind[]) => void;
};

const EnterpriseContext = createContext<EnterpriseContextValue | null>(null);

function parseUrlEnterpriseId(pathname: string, searchParams: URLSearchParams): number | null {
  const searchValue = searchParams.get("enterpriseId");
  if (searchValue && Number.isFinite(Number(searchValue))) {
    return Number(searchValue);
  }

  const match = pathname.match(/\/enterprises\/(\d+)/);
  if (match) {
    return Number(match[1]);
  }

  return null;
}

export function EnterpriseProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchParamsKey = searchParams.toString();

  const [enterpriseOptions, setEnterpriseOptions] = useState<EnterpriseSearchItem[]>([]);
  const [allEnterpriseOptions, setAllEnterpriseOptions] = useState<EnterpriseSearchItem[]>([]);
  const [currentEnterpriseId, setCurrentEnterpriseId] = useState<number | null>(null);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [enterpriseLoading, setEnterpriseLoading] = useState(true);
  const [enterpriseError, setEnterpriseError] = useState<string | null>(null);

  const searchCacheRef = useRef<Map<string, { items: EnterpriseSearchItem[]; fetchedAt: number }>>(new Map());
  const autoSyncTriggeredRef = useRef<Set<number>>(new Set());
  const resourceCacheRef = useRef<{
    dashboard: Map<number, DashboardPayload>;
    riskResults: Map<number, RiskResultPayload[]>;
    auditFocus: Map<number, AuditFocusPayload>;
    documents: Map<number, DocumentListItem[]>;
    readiness: Map<number, EnterpriseReadinessPayload>;
  }>({
    dashboard: new Map(),
    riskResults: new Map(),
    auditFocus: new Map(),
    documents: new Map(),
    readiness: new Map(),
  });

  const urlEnterpriseId = useMemo(() => {
    return parseUrlEnterpriseId(pathname, new URLSearchParams(searchParamsKey));
  }, [pathname, searchParamsKey]);

  const refreshEnterpriseOptions = useCallback(async (query = "", options?: { force?: boolean }) => {
    const normalized = query.trim().toLowerCase();
    const cached = searchCacheRef.current.get(normalized);
    if (!options?.force && cached && Date.now() - cached.fetchedAt < SEARCH_CACHE_TTL) {
      setEnterpriseOptions(cached.items);
      if (!normalized) {
        setAllEnterpriseOptions(cached.items);
      }
      return cached.items;
    }

    const items = await api.listEnterprises(query);
    searchCacheRef.current.set(normalized, { items, fetchedAt: Date.now() });
    setEnterpriseOptions(items);
    if (!normalized) {
      setAllEnterpriseOptions(items);
    }
    return items;
  }, []);

  const selectEnterprise = useCallback(
    (enterpriseId: number) => {
      setCurrentEnterpriseId(enterpriseId);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(ENTERPRISE_STORAGE_KEY, String(enterpriseId));
      }
      if (pathname.startsWith("/enterprises/")) {
        router.replace(`/enterprises/${enterpriseId}`);
      }
    },
    [pathname, router],
  );

  const bootstrapEnterprise = useCallback(
    async (payload: { ticker?: string; name?: string }) => {
      const result = await api.bootstrapEnterprise(payload);
      const items = await refreshEnterpriseOptions("", { force: true });
      const enterprise =
        items.find((item) => item.id === result.enterprise_id) ?? {
          id: result.enterprise_id,
          name: result.name,
          ticker: result.ticker,
          industry_tag: result.industry_tag,
          report_year: new Date().getFullYear(),
        };
      selectEnterprise(enterprise.id);
      return enterprise;
    },
    [refreshEnterpriseOptions, selectEnterprise],
  );

  useEffect(() => {
    let cancelled = false;

    async function initialize() {
      setEnterpriseLoading(true);
      setEnterpriseError(null);

      try {
        const items = await refreshEnterpriseOptions("", { force: true });
        if (cancelled) {
          return;
        }

        if (items.length === 0) {
          setCurrentEnterpriseId(null);
          return;
        }

        const storedEnterpriseId =
          typeof window !== "undefined" ? Number(window.localStorage.getItem(ENTERPRISE_STORAGE_KEY)) : null;
        const nextEnterpriseId =
          (urlEnterpriseId && items.some((item) => item.id === urlEnterpriseId) && urlEnterpriseId) ||
          (storedEnterpriseId && items.some((item) => item.id === storedEnterpriseId) && storedEnterpriseId) ||
          items[0]?.id ||
          null;

        setCurrentEnterpriseId(nextEnterpriseId);
        if (typeof window !== "undefined" && nextEnterpriseId) {
          window.localStorage.setItem(ENTERPRISE_STORAGE_KEY, String(nextEnterpriseId));
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        setEnterpriseOptions([]);
        setAllEnterpriseOptions([]);
        setCurrentEnterpriseId(null);
        setEnterpriseError(error instanceof Error ? error.message : "企业列表加载失败。");
      } finally {
        if (!cancelled) {
          setEnterpriseLoading(false);
        }
      }
    }

    void initialize();
    return () => {
      cancelled = true;
    };
  }, [refreshEnterpriseOptions, urlEnterpriseId]);

  useEffect(() => {
    if (!urlEnterpriseId || currentEnterpriseId === urlEnterpriseId) {
      return;
    }
    const exists = enterpriseOptions.some((item) => item.id === urlEnterpriseId);
    if (exists) {
      setCurrentEnterpriseId(urlEnterpriseId);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(ENTERPRISE_STORAGE_KEY, String(urlEnterpriseId));
      }
    }
  }, [currentEnterpriseId, enterpriseOptions, urlEnterpriseId]);

  useEffect(() => {
    let active = true;

    async function maybeAutoSync() {
      if (!currentEnterpriseId || autoSyncTriggeredRef.current.has(currentEnterpriseId)) {
        return;
      }

      try {
        const readiness = await api.getReadiness(currentEnterpriseId);
        if (!active) {
          return;
        }
        resourceCacheRef.current.readiness.set(currentEnterpriseId, readiness);
        if (readiness.profile_ready && readiness.official_doc_count === 0 && readiness.sync_status !== "syncing") {
          autoSyncTriggeredRef.current.add(currentEnterpriseId);
          const result = await api.syncCompany(currentEnterpriseId);
          resourceCacheRef.current.readiness.delete(currentEnterpriseId);
          if (result.documents_inserted > 0 || result.events_inserted > 0 || result.announcements_fetched > 0) {
            resourceCacheRef.current.documents.delete(currentEnterpriseId);
            resourceCacheRef.current.dashboard.delete(currentEnterpriseId);
            resourceCacheRef.current.auditFocus.delete(currentEnterpriseId);
            resourceCacheRef.current.riskResults.delete(currentEnterpriseId);
          }
        }
      } catch {
        // Keep pages usable; page-level resources will show their own state.
      }
    }

    void maybeAutoSync();
    return () => {
      active = false;
    };
  }, [currentEnterpriseId]);

  const currentEnterprise = useMemo(
    () =>
      allEnterpriseOptions.find((item) => item.id === currentEnterpriseId) ??
      enterpriseOptions.find((item) => item.id === currentEnterpriseId) ??
      null,
    [allEnterpriseOptions, currentEnterpriseId, enterpriseOptions],
  );

  const getCachedResource = useCallback(<T,>(kind: ResourceKind, enterpriseId: number): T | null => {
    return (resourceCacheRef.current[kind].get(enterpriseId) as T | undefined) ?? null;
  }, []);

  const setCachedResource = useCallback(<T,>(kind: ResourceKind, enterpriseId: number, value: T) => {
    resourceCacheRef.current[kind].set(enterpriseId, value as never);
  }, []);

  const invalidateEnterpriseResources = useCallback((enterpriseId: number, kinds?: ResourceKind[]) => {
    const targets = kinds ?? ["dashboard", "riskResults", "auditFocus", "documents", "readiness"];
    for (const kind of targets) {
      resourceCacheRef.current[kind].delete(enterpriseId);
    }
  }, []);

  const value = useMemo<EnterpriseContextValue>(
    () => ({
      currentEnterpriseId,
      currentEnterprise,
      enterpriseOptions,
      searchKeyword,
      enterpriseLoading,
      enterpriseError,
      selectEnterprise,
      setSearchKeyword,
      refreshEnterpriseOptions,
      bootstrapEnterprise,
      getCachedResource,
      setCachedResource,
      invalidateEnterpriseResources,
    }),
    [
      bootstrapEnterprise,
      currentEnterprise,
      currentEnterpriseId,
      enterpriseError,
      enterpriseLoading,
      enterpriseOptions,
      getCachedResource,
      invalidateEnterpriseResources,
      refreshEnterpriseOptions,
      searchKeyword,
      selectEnterprise,
      setCachedResource,
    ],
  );

  return <EnterpriseContext.Provider value={value}>{children}</EnterpriseContext.Provider>;
}

export function useEnterpriseContext() {
  const context = useContext(EnterpriseContext);
  if (!context) {
    throw new Error("useEnterpriseContext must be used within EnterpriseProvider");
  }
  return context;
}
