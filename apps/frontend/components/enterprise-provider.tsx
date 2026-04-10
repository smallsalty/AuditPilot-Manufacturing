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
  EnterpriseSearchItem,
  RiskResultPayload,
} from "@auditpilot/shared-types";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";

import { api } from "@/lib/api";

const ENTERPRISE_STORAGE_KEY = "auditpilot.currentEnterpriseId";
const SEARCH_CACHE_TTL = 30_000;

type ResourceKind = "dashboard" | "riskResults" | "auditFocus" | "documents";

type EnterpriseContextValue = EnterpriseContextState & {
  selectEnterprise: (enterpriseId: number) => void;
  setSearchKeyword: (value: string) => void;
  refreshEnterpriseOptions: (query?: string, options?: { force?: boolean }) => Promise<EnterpriseSearchItem[]>;
  getCachedResource: <T>(kind: ResourceKind, enterpriseId: number) => T | null;
  setCachedResource: <T>(kind: ResourceKind, enterpriseId: number, value: T) => void;
  invalidateEnterpriseResources: (enterpriseId: number, kinds?: ResourceKind[]) => void;
};

const EnterpriseContext = createContext<EnterpriseContextValue | null>(null);

function parseUrlEnterpriseId(pathname: string, params: Record<string, string | string[] | undefined>, search: URLSearchParams): number | null {
  const searchValue = search.get("enterpriseId");
  if (searchValue && Number.isFinite(Number(searchValue))) {
    return Number(searchValue);
  }

  const paramValue = params.id;
  if (typeof paramValue === "string" && Number.isFinite(Number(paramValue))) {
    return Number(paramValue);
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
  const params = useParams();
  const searchParams = useSearchParams();

  const [enterpriseOptions, setEnterpriseOptions] = useState<EnterpriseSearchItem[]>([]);
  const [allEnterpriseOptions, setAllEnterpriseOptions] = useState<EnterpriseSearchItem[]>([]);
  const [currentEnterpriseId, setCurrentEnterpriseId] = useState<number | null>(null);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [enterpriseLoading, setEnterpriseLoading] = useState(true);
  const [enterpriseError, setEnterpriseError] = useState<string | null>(null);

  const searchCacheRef = useRef<Map<string, { items: EnterpriseSearchItem[]; fetchedAt: number }>>(new Map());
  const resourceCacheRef = useRef<{
    dashboard: Map<number, DashboardPayload>;
    riskResults: Map<number, RiskResultPayload[]>;
    auditFocus: Map<number, AuditFocusPayload>;
    documents: Map<number, DocumentListItem[]>;
  }>({
    dashboard: new Map(),
    riskResults: new Map(),
    auditFocus: new Map(),
    documents: new Map(),
  });

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

  const refreshEnterpriseOptions = useCallback(
    async (query = "", options?: { force?: boolean }) => {
      const normalized = query.trim().toLowerCase();
      const cached = searchCacheRef.current.get(normalized);
      if (!options?.force && cached && Date.now() - cached.fetchedAt < SEARCH_CACHE_TTL) {
        setEnterpriseOptions(cached.items);
        return cached.items;
      }

      const items = await api.listEnterprises(query);
      searchCacheRef.current.set(normalized, { items, fetchedAt: Date.now() });
      setEnterpriseOptions(items);
      if (!normalized) {
        setAllEnterpriseOptions(items);
      }
      return items;
    },
    [],
  );

  useEffect(() => {
    let active = true;
    async function initialize() {
      setEnterpriseLoading(true);
      setEnterpriseError(null);
      try {
        const items = await refreshEnterpriseOptions("", { force: true });
        if (!active) return;
        if (items.length === 0) {
          setCurrentEnterpriseId(null);
          return;
        }

        const urlEnterpriseId = parseUrlEnterpriseId(pathname, params, searchParams);
        const localEnterpriseId =
          typeof window !== "undefined" ? Number(window.localStorage.getItem(ENTERPRISE_STORAGE_KEY)) : null;
        const nextEnterpriseId =
          (urlEnterpriseId && items.some((item) => item.id === urlEnterpriseId) && urlEnterpriseId) ||
          (localEnterpriseId && items.some((item) => item.id === localEnterpriseId) && localEnterpriseId) ||
          items[0]?.id ||
          null;

        setCurrentEnterpriseId(nextEnterpriseId);
        if (typeof window !== "undefined" && nextEnterpriseId) {
          window.localStorage.setItem(ENTERPRISE_STORAGE_KEY, String(nextEnterpriseId));
        }
      } catch (error) {
        if (!active) return;
        setEnterpriseOptions([]);
        setCurrentEnterpriseId(null);
        setEnterpriseError(error instanceof Error ? error.message : "企业列表加载失败");
      } finally {
        if (active) {
          setEnterpriseLoading(false);
        }
      }
    }

    initialize();
    return () => {
      active = false;
    };
  }, [pathname, params, refreshEnterpriseOptions, searchParams]);

  useEffect(() => {
    const urlEnterpriseId = parseUrlEnterpriseId(pathname, params, searchParams);
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
  }, [currentEnterpriseId, enterpriseOptions, pathname, params, searchParams]);

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
    const targets = kinds ?? ["dashboard", "riskResults", "auditFocus", "documents"];
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
      getCachedResource,
      setCachedResource,
      invalidateEnterpriseResources,
    }),
    [
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
