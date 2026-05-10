"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, setApiSessionToken } from "@/lib/api";
import type {
  EnterpriseSession,
  LoginRequest,
  PasswordChangeRequest,
  PasswordResetConfirmRequest,
  RecoveryRequest,
  SessionRevokeRequest,
  UserSessionRecord,
} from "@/types";

const ANONYMOUS_USER: EnterpriseSession["user"] = {
  user_id: "anonymous",
  name: "Visitante",
  email: "",
  role: "viewer",
  permissions: [],
};

const EMPTY_TENANT: EnterpriseSession["active_tenant"] = {
  tenant_id: "default",
  name: "Workspace Principal",
  workspace_id: "default",
  plan: "enterprise",
  status: "active",
  operational_retention_mode: "keep_latest",
  operational_retention_hours: 24,
  document_count: 0,
};

const LOCAL_TENANTS: EnterpriseSession["available_tenants"] = [
  EMPTY_TENANT,
  {
    tenant_id: "acme-lab",
    name: "Acme Lab",
    workspace_id: "acme-lab",
    plan: "business",
    status: "active",
    operational_retention_mode: "keep_latest",
    operational_retention_hours: 24,
    document_count: 0,
  },
  {
    tenant_id: "northwind",
    name: "Northwind Pilot",
    workspace_id: "northwind",
    plan: "starter",
    status: "active",
    operational_retention_mode: "keep_latest",
    operational_retention_hours: 24,
    document_count: 0,
  },
];

function isExpired(expiresAt?: string | null) {
  if (!expiresAt) return false;
  const parsed = Date.parse(expiresAt);
  return Number.isFinite(parsed) && parsed <= Date.now();
}

function asAnonymousSession(source: EnterpriseSession | null): EnterpriseSession {
  return {
    authenticated: false,
    session_state: "anonymous",
    expires_at: null,
    session_token: null,
    user: ANONYMOUS_USER,
    active_tenant: source?.active_tenant ?? EMPTY_TENANT,
    available_tenants: source?.available_tenants ?? LOCAL_TENANTS,
    message: "Sessão expirada. Faça login para continuar.",
  };
}

function normalizeSession(source: EnterpriseSession | null): EnterpriseSession {
  if (!source) return asAnonymousSession(null);
  if (source.session_state === "expired" || isExpired(source.expires_at)) {
    return {
      ...asAnonymousSession(source),
      session_state: "expired",
      message: "Sessão expirada. Faça login novamente para continuar.",
    };
  }
  return source;
}

type EnterpriseSessionContextValue = {
  session: EnterpriseSession | null;
  ready: boolean;
  signIn: (request: LoginRequest) => Promise<EnterpriseSession>;
  signOut: () => Promise<void>;
  switchTenant: (tenantId: string) => Promise<void>;
  requestRecovery: (request: RecoveryRequest) => Promise<string>;
  confirmPasswordReset: (request: PasswordResetConfirmRequest) => Promise<string>;
  changePassword: (request: PasswordChangeRequest) => Promise<string>;
  listSessions: () => Promise<UserSessionRecord[]>;
  revokeSessions: (request: SessionRevokeRequest) => Promise<string>;
  refresh: () => Promise<void>;
};

const EnterpriseSessionContext = createContext<EnterpriseSessionContextValue | null>(null);

export function EnterpriseSessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<EnterpriseSession | null>(null);
  const [ready, setReady] = useState(false);
  const bootstrapRequestRef = useRef(0);

  useEffect(() => {
    let active = true;
    const requestId = bootstrapRequestRef.current + 1;
    bootstrapRequestRef.current = requestId;

    api.session
      .current()
      .then((response) => {
        if (!active || bootstrapRequestRef.current !== requestId) return;
        const normalized = normalizeSession(response);
        setApiSessionToken(normalized.authenticated ? normalized.session_token : null);
        setSession(normalized);
      })
      .catch(() => {
        if (!active || bootstrapRequestRef.current !== requestId) return;
        setApiSessionToken(null);
        setSession(asAnonymousSession(null));
      })
      .finally(() => {
        if (active && bootstrapRequestRef.current === requestId) setReady(true);
      });

    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<EnterpriseSessionContextValue>(() => {
    return {
      session,
      ready,
      signIn: async (request: LoginRequest) => {
        bootstrapRequestRef.current += 1;
        const response = await api.session.login(request);
        const normalized = normalizeSession(response);
        setApiSessionToken(normalized.authenticated ? normalized.session_token : null);
        setSession(normalized);
        return normalized;
      },
      signOut: async () => {
        bootstrapRequestRef.current += 1;
        try {
          await api.session.logout();
        } catch {
          // Best effort only.
        }
        setApiSessionToken(null);
        setSession((current) => asAnonymousSession(current));
      },
      switchTenant: async (tenantId: string) => {
        bootstrapRequestRef.current += 1;
        const response = await api.session.switchTenant(tenantId);
        const normalized = normalizeSession(response);
        setApiSessionToken(normalized.authenticated ? normalized.session_token : null);
        setSession(normalized);
      },
      requestRecovery: async (request: RecoveryRequest) => {
        const response = await api.session.requestPasswordReset({ email: request.email, tenant_id: request.tenant_id });
        return response.message;
      },
      confirmPasswordReset: async (request: PasswordResetConfirmRequest) => {
        const response = await api.session.confirmPasswordReset(request);
        return response.message;
      },
      changePassword: async (request: PasswordChangeRequest) => {
        const response = await api.session.changePassword(request);
        setApiSessionToken(null);
        setSession((current) => asAnonymousSession(current));
        return response.message;
      },
      listSessions: async () => {
        const response = await api.session.sessions();
        return response.items;
      },
      revokeSessions: async (request: SessionRevokeRequest) => {
        const response = await api.session.revokeSessions(request);
        return response.message;
      },
      refresh: async () => {
        bootstrapRequestRef.current += 1;
        const response = await api.session.current();
        const normalized = normalizeSession(response);
        setApiSessionToken(normalized.authenticated ? normalized.session_token : null);
        setSession(normalized);
      },
    };
  }, [ready, session]);

  return <EnterpriseSessionContext.Provider value={value}>{children}</EnterpriseSessionContext.Provider>;
}

export function useEnterpriseSession() {
  const context = useContext(EnterpriseSessionContext);
  if (!context) {
    throw new Error("useEnterpriseSession must be used within EnterpriseSessionProvider");
  }
  return context;
}
