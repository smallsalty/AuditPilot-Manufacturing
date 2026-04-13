"use client";

import { useCallback, useEffect, useState } from "react";
import type {
  AuditFocusPayload,
  DashboardPayload,
  DocumentListItem,
  EnterpriseReadinessPayload,
  RiskResultPayload,
} from "@auditpilot/shared-types";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { api } from "@/lib/api";

type ResourceKind = "dashboard" | "riskResults" | "auditFocus" | "documents" | "readiness";

type ResourceState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

function useCachedEnterpriseResource<T>(
  kind: ResourceKind,
  enterpriseId: number | null,
  fetcher: (enterpriseId: number) => Promise<T>,
): ResourceState<T> {
  const { getCachedResource, setCachedResource } = useEnterpriseContext();
  const [data, setData] = useState<T | null>(enterpriseId ? getCachedResource<T>(kind, enterpriseId) : null);
  const [loading, setLoading] = useState(Boolean(enterpriseId && !getCachedResource<T>(kind, enterpriseId)));
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enterpriseId) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    const cached = getCachedResource<T>(kind, enterpriseId);
    if (cached) {
      setData(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    try {
      const payload = await fetcher(enterpriseId);
      setCachedResource(kind, enterpriseId, payload);
      setData(payload);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "数据加载失败");
      if (!cached) {
        setData(null);
      }
    } finally {
      setLoading(false);
    }
  }, [enterpriseId, fetcher, getCachedResource, kind, setCachedResource]);

  useEffect(() => {
    setData(enterpriseId ? getCachedResource<T>(kind, enterpriseId) : null);
    setError(null);
    void refresh();
  }, [enterpriseId, getCachedResource, kind, refresh]);

  return { data, loading, error, refresh };
}

export function useDashboardResource(enterpriseId: number | null) {
  return useCachedEnterpriseResource<DashboardPayload>("dashboard", enterpriseId, api.getDashboard);
}

export function useRiskResultsResource(enterpriseId: number | null) {
  return useCachedEnterpriseResource<RiskResultPayload[]>("riskResults", enterpriseId, api.getRiskResults);
}

export function useAuditFocusResource(enterpriseId: number | null) {
  return useCachedEnterpriseResource<AuditFocusPayload>("auditFocus", enterpriseId, api.getAuditFocus);
}

export function useDocumentsResource(enterpriseId: number | null) {
  return useCachedEnterpriseResource<DocumentListItem[]>("documents", enterpriseId, api.getEnterpriseDocuments);
}

export function useReadinessResource(enterpriseId: number | null) {
  return useCachedEnterpriseResource<EnterpriseReadinessPayload>("readiness", enterpriseId, api.getReadiness);
}
