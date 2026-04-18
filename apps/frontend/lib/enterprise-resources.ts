"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AuditFocusPayload,
  DashboardPayload,
  DocumentListItem,
  EnterpriseEventsPayload,
  EnterpriseReadinessPayload,
  FinancialAnalysisPayload,
  RiskResultPayload,
} from "@auditpilot/shared-types";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { api, type ApiRequestOptions } from "@/lib/api";

type ResourceKind = "dashboard" | "riskResults" | "auditFocus" | "documents" | "events" | "readiness" | "financialAnalysis";

type ResourceState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  refresh: (options?: { force?: boolean }) => Promise<void>;
};

type ResourceFetcher<T> = (enterpriseId: number, options?: ApiRequestOptions) => Promise<T>;

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function useCachedEnterpriseResource<T>(
  kind: ResourceKind,
  enterpriseId: number | null,
  fetcher: ResourceFetcher<T>,
): ResourceState<T> {
  const { currentEnterpriseId: activeEnterpriseId, getCachedResource, setCachedResource } = useEnterpriseContext();
  const [data, setData] = useState<T | null>(enterpriseId ? getCachedResource<T>(kind, enterpriseId) : null);
  const [loading, setLoading] = useState(Boolean(enterpriseId && !getCachedResource<T>(kind, enterpriseId)));
  const [error, setError] = useState<string | null>(null);

  const requestIdRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  const refresh = useCallback(
    async (options?: { force?: boolean }) => {
      if (!enterpriseId) {
        requestIdRef.current += 1;
        abortControllerRef.current?.abort();
        abortControllerRef.current = null;
        setData(null);
        setLoading(false);
        setError(null);
        return;
      }

      requestIdRef.current += 1;
      const requestId = requestIdRef.current;
      abortControllerRef.current?.abort();
      const controller = new AbortController();
      abortControllerRef.current = controller;

      const cached = !options?.force ? getCachedResource<T>(kind, enterpriseId) : null;
      if (cached) {
        setData(cached);
        setLoading(false);
      } else {
        setData(null);
        setLoading(true);
      }
      setError(null);

      try {
        const payload = await fetcher(enterpriseId, {
          signal: controller.signal,
          force: options?.force,
        });
        if (requestIdRef.current !== requestId || controller.signal.aborted) {
          console.info(
            "stale enterprise response dropped",
            JSON.stringify({
              kind,
              requested_enterprise_id: enterpriseId,
              current_enterprise_id: activeEnterpriseId,
              reason: controller.signal.aborted ? "aborted" : "request_id_mismatch",
            }),
          );
          return;
        }
        setCachedResource(kind, enterpriseId, payload);
        setData(payload);
        setError(null);
      } catch (err) {
        if (requestIdRef.current !== requestId || controller.signal.aborted || isAbortError(err)) {
          if (requestIdRef.current !== requestId || controller.signal.aborted) {
            console.info(
              "stale enterprise response dropped",
              JSON.stringify({
                kind,
                requested_enterprise_id: enterpriseId,
                current_enterprise_id: activeEnterpriseId,
                reason: controller.signal.aborted ? "aborted" : "request_id_mismatch",
              }),
            );
          }
          return;
        }
        setError(err instanceof Error ? err.message : "数据加载失败");
        if (!cached) {
          setData(null);
        }
      } finally {
        if (requestIdRef.current === requestId) {
          setLoading(false);
        }
      }
    },
    [activeEnterpriseId, enterpriseId, fetcher, getCachedResource, kind, setCachedResource],
  );

  useEffect(() => {
    requestIdRef.current += 1;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setError(null);

    if (!enterpriseId) {
      setData(null);
      setLoading(false);
      return;
    }

    const cached = getCachedResource<T>(kind, enterpriseId);
    setData(cached);
    setLoading(!cached);
    void refresh();

    return () => {
      requestIdRef.current += 1;
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
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

export function useEventsResource(enterpriseId: number | null) {
  return useCachedEnterpriseResource<EnterpriseEventsPayload>("events", enterpriseId, api.getEnterpriseEvents);
}

export function useReadinessResource(enterpriseId: number | null) {
  return useCachedEnterpriseResource<EnterpriseReadinessPayload>("readiness", enterpriseId, api.getReadiness);
}

export function useFinancialAnalysisResource(enterpriseId: number | null) {
  return useCachedEnterpriseResource<FinancialAnalysisPayload>("financialAnalysis", enterpriseId, api.getFinancialAnalysis);
}
