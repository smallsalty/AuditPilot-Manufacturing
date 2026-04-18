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
  EnterpriseEventsPayload,
  EnterpriseReadinessPayload,
  EnterpriseSearchItem,
  FinancialAnalysisPayload,
  RiskResultPayload,
} from "@auditpilot/shared-types";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { api } from "@/lib/api";

const ENTERPRISE_STORAGE_KEY = "auditpilot.currentEnterpriseId";
const SEARCH_CACHE_TTL = 30_000;

type ResourceKind = "dashboard" | "riskResults" | "auditFocus" | "documents" | "events" | "readiness" | "financialAnalysis";

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
  const [defaultEnterpriseOptions, setDefaultEnterpriseOptions] = useState<EnterpriseSearchItem[]>([]);
  const [currentEnterpriseId, setCurrentEnterpriseId] = useState<number | null>(null);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [enterpriseLoading, setEnterpriseLoading] = useState(true);
  const [enterpriseError, setEnterpriseError] = useState<string | null>(null);

  const selectionVersionRef = useRef(0);
  const searchCacheRef = useRef<Map<string, { items: EnterpriseSearchItem[]; fetchedAt: number }>>(new Map());
  const autoSyncTriggeredRef = useRef<Set<number>>(new Set());
  const initializedRef = useRef(false);
  const resourceCacheRef = useRef<{
    dashboard: Map<number, DashboardPayload>;
    riskResults: Map<number, RiskResultPayload[]>;
    auditFocus: Map<number, AuditFocusPayload>;
    documents: Map<number, DocumentListItem[]>;
    events: Map<number, EnterpriseEventsPayload>;
    readiness: Map<number, EnterpriseReadinessPayload>;
    financialAnalysis: Map<number, FinancialAnalysisPayload>;
  }>({
    dashboard: new Map(),
    riskResults: new Map(),
    auditFocus: new Map(),
    documents: new Map(),
    events: new Map(),
    readiness: new Map(),
    financialAnalysis: new Map(),
  });

  const urlEnterpriseId = useMemo(
    () => parseUrlEnterpriseId(pathname, new URLSearchParams(searchParamsKey)),
    [pathname, searchParamsKey],
  );

  const invalidateEnterpriseResources = useCallback((enterpriseId: number, kinds?: ResourceKind[]) => {
    const targets = kinds ?? ["dashboard", "riskResults", "auditFocus", "documents", "events", "readiness", "financialAnalysis"];
    for (const kind of targets) {
      resourceCacheRef.current[kind].delete(enterpriseId);
    }
    if (!kinds || kinds.includes("financialAnalysis")) {
      api.invalidateFinancialAnalysis(enterpriseId);
    }
  }, []);

  const refreshEnterpriseOptions = useCallback(async (query = "", options?: { force?: boolean }) => {
    const normalized = query.trim().toLowerCase();
    const cached = searchCacheRef.current.get(normalized);
    if (!options?.force && cached && Date.now() - cached.fetchedAt < SEARCH_CACHE_TTL) {
      if (normalized) {
        setEnterpriseOptions(cached.items);
      } else {
        setDefaultEnterpriseOptions(cached.items);
        setEnterpriseOptions(cached.items);
      }
      return cached.items;
    }

    const items = await api.listEnterprises(query);
    searchCacheRef.current.set(normalized, { items, fetchedAt: Date.now() });
    if (normalized) {
      setEnterpriseOptions(items);
    } else {
      setDefaultEnterpriseOptions(items);
      setEnterpriseOptions(items);
    }
    return items;
  }, []);

  const selectEnterprise = useCallback(
    (enterpriseId: number) => {
      if (!Number.isFinite(enterpriseId) || enterpriseId <= 0) {
        return;
      }
      if (currentEnterpriseId === enterpriseId) {
        return;
      }

      selectionVersionRef.current += 1;
      if (currentEnterpriseId) {
        invalidateEnterpriseResources(currentEnterpriseId);
      }
      invalidateEnterpriseResources(enterpriseId);

      setCurrentEnterpriseId(enterpriseId);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(ENTERPRISE_STORAGE_KEY, String(enterpriseId));
      }
      if (pathname.startsWith("/enterprises/")) {
        router.replace(`/enterprises/${enterpriseId}`);
      } else if (searchParams.get("enterpriseId") !== String(enterpriseId)) {
        router.replace(`${pathname}?enterpriseId=${enterpriseId}`);
      }
    },
    [currentEnterpriseId, invalidateEnterpriseResources, pathname, router, searchParams],
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
          initializedRef.current = true;
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
        initializedRef.current = true;
      } catch (error) {
        if (cancelled) {
          return;
        }
        setDefaultEnterpriseOptions([]);
        setEnterpriseOptions([]);
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
    if (!initializedRef.current || !urlEnterpriseId || currentEnterpriseId === urlEnterpriseId) {
      return;
    }
    const exists =
      defaultEnterpriseOptions.some((item) => item.id === urlEnterpriseId) ||
      enterpriseOptions.some((item) => item.id === urlEnterpriseId);
    if (!exists) {
      return;
    }
    selectionVersionRef.current += 1;
    setCurrentEnterpriseId(urlEnterpriseId);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ENTERPRISE_STORAGE_KEY, String(urlEnterpriseId));
    }
  }, [currentEnterpriseId, defaultEnterpriseOptions, enterpriseOptions, urlEnterpriseId]);

  useEffect(() => {
    if (!currentEnterpriseId || !initializedRef.current || autoSyncTriggeredRef.current.has(currentEnterpriseId)) {
      return;
    }

    const enterpriseId = currentEnterpriseId;
    const controller = new AbortController();
    const selectionVersion = selectionVersionRef.current;

    async function maybeAutoSync() {
      try {
        const readiness = await api.getReadiness(enterpriseId, { signal: controller.signal });
        if (controller.signal.aborted || selectionVersionRef.current !== selectionVersion) {
          return;
        }
        resourceCacheRef.current.readiness.set(enterpriseId, readiness);
        if (!readiness.profile_ready || readiness.official_doc_count > 0 || readiness.sync_status === "syncing") {
          return;
        }

        autoSyncTriggeredRef.current.add(enterpriseId);
        const result = await api.syncCompany(enterpriseId, ["akshare_fast", "cninfo"], {
          signal: controller.signal,
        });
        if (controller.signal.aborted || selectionVersionRef.current !== selectionVersion) {
          return;
        }
        invalidateEnterpriseResources(enterpriseId, ["readiness"]);
        if (result.documents_inserted > 0 || result.events_inserted > 0 || result.announcements_fetched > 0) {
          invalidateEnterpriseResources(enterpriseId, [
            "documents",
            "events",
            "dashboard",
            "auditFocus",
            "riskResults",
            "financialAnalysis",
          ]);
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        // page-level resources surface user-facing errors
      }
    }

    void maybeAutoSync();
    return () => {
      controller.abort();
    };
  }, [currentEnterpriseId, invalidateEnterpriseResources]);

  const currentEnterprise = useMemo(
    () =>
      defaultEnterpriseOptions.find((item) => item.id === currentEnterpriseId) ??
      enterpriseOptions.find((item) => item.id === currentEnterpriseId) ??
      null,
    [currentEnterpriseId, defaultEnterpriseOptions, enterpriseOptions],
  );

  const getCachedResource = useCallback(<T,>(kind: ResourceKind, enterpriseId: number): T | null => {
    return (resourceCacheRef.current[kind].get(enterpriseId) as T | undefined) ?? null;
  }, []);

  const setCachedResource = useCallback(<T,>(kind: ResourceKind, enterpriseId: number, value: T) => {
    resourceCacheRef.current[kind].set(enterpriseId, value as never);
  }, []);

  const value = useMemo<EnterpriseContextValue>(
    () => ({
      currentEnterpriseId,
      currentEnterprise,
      enterpriseOptions: searchKeyword.trim() ? enterpriseOptions : defaultEnterpriseOptions,
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
      defaultEnterpriseOptions,
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
