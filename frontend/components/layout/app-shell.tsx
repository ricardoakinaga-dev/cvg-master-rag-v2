"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Suspense, useEffect, useState, type ComponentType, type ReactNode } from "react";
import { ActivitySquare, BookOpenText, Building2, LayoutDashboard, LogOut, MessageSquareText, Search, ShieldAlert, UserRound } from "lucide-react";
import { EnterpriseSessionProvider, useEnterpriseSession } from "@/components/layout/enterprise-session-provider";
import { Badge, Button, Card, Drawer, Select, ToastProvider, ToastViewport } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { getAllowedNavItems, getBreadcrumbs, isRouteAllowed, ROUTE_META, type AppRoute } from "@/lib/navigation";

const ICONS: Record<string, ComponentType<{ size?: number }>> = {
  "/": ActivitySquare,
  "/documents": BookOpenText,
  "/search": Search,
  "/chat": MessageSquareText,
  "/admin": ShieldAlert,
  "/dashboard": LayoutDashboard,
  "/audit": ShieldAlert,
};

const AUTH_ROUTES = new Set(["/login", "/onboarding", "/recover-access", "/forbidden"]);

function AppShellFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const route = ROUTE_META[pathname] ?? ROUTE_META["/"];
  const { session, ready, signOut, switchTenant } = useEnterpriseSession();
  const [health, setHealth] = useState<Awaited<ReturnType<typeof api.health>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [currentSearch, setCurrentSearch] = useState("");
  const activeWorkspaceId = session?.active_tenant.workspace_id ?? "default";

  useEffect(() => {
    let active = true;
    setError(null);
    api
      .health(activeWorkspaceId, { light: true })
      .then((value) => {
        if (active) {
          setHealth(value);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Falha ao carregar health");
      });

    return () => {
      active = false;
    };
  }, [activeWorkspaceId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setCurrentSearch(window.location.search);
  }, [pathname]);

  useEffect(() => {
    if (!ready || AUTH_ROUTES.has(pathname)) return;
    if (!session || !session.authenticated || session.session_state !== "active") {
      const target = `${pathname}${currentSearch}`;
      router.replace(`/login?next=${encodeURIComponent(target)}`);
      return;
    }
    if (!isRouteAllowed(pathname, session.user.role)) {
      router.replace(`/forbidden?from=${encodeURIComponent(pathname)}`);
    }
  }, [currentSearch, pathname, ready, router, session]);

  if (AUTH_ROUTES.has(pathname)) {
    return <>{children}</>;
  }

  if (!ready || !session || !session.authenticated || session.session_state !== "active") {
    return (
      <div className="auth-page">
        <div className="auth-shell auth-shell-single">
          <Card className="auth-panel">
            <div className="state-box">
              <h3>Carregando sessão</h3>
              <p>Validando identidade, tenant e permissões antes de abrir o console.</p>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  const CurrentIcon = ICONS[pathname] ?? ActivitySquare;
  const breadcrumbs = getBreadcrumbs(pathname);
  const roleLabel = session?.user.role ?? "carregando";
  const activeTenantLabel = session?.active_tenant.name ?? "carregando";
  const activeWorkspaceLabel = session?.active_tenant.workspace_id ?? "carregando";
  const availableTenants = session?.available_tenants ?? [];
  const navItems = getAllowedNavItems(session.user.role);
  return (
    <div className="app-shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">RAG</div>
            <div className="brand-title">
              <strong>Premium Console</strong>
              <span>Fase 3 enterprise</span>
            </div>
          </div>

          <nav className="nav-group" aria-label="Navegação principal">
            <div className="nav-group-title">Módulos</div>
            {navItems.map((item) => {
              const active = pathname === item.href;
              const Icon = ICONS[item.href] ?? ActivitySquare;
              return (
                <Link key={item.href} href={item.href} className={active ? "nav-link active" : "nav-link"}>
                  <Icon size={18} />
                  <span>
                    <strong>{item.label}</strong>
                    <br />
                    <small>{item.description}</small>
                  </span>
                </Link>
              );
            })}
          </nav>

          <Card className="card-inner">
            <div className="card-title">
              <strong>API base</strong>
              <span>{process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}</span>
            </div>
            <p className="thin">Frontend configurado para consumir o backend local por REST.</p>
          </Card>

          <Card className="card-inner session-card">
            <div className="card-title">
              <strong>{session?.user.name ?? "Sessão enterprise"}</strong>
              <span>{session?.user.email || "Identidade carregada no shell"}</span>
            </div>
            <div className="session-meta">
              <Badge variant="info">
                <UserRound size={14} />
                {roleLabel}
              </Badge>
              <Badge variant="neutral">
                <Building2 size={14} />
                {activeWorkspaceLabel}
              </Badge>
            </div>
            <label className="ui-label">
              Tenant ativo
              <Select
                value={session?.active_tenant.tenant_id ?? ""}
                onChange={(event) => {
                  void switchTenant(event.target.value);
                }}
                disabled={!ready || !availableTenants.length}
              >
                {availableTenants.map((tenant) => (
                  <option key={tenant.tenant_id} value={tenant.tenant_id}>
                    {tenant.name} · {tenant.workspace_id}
                  </option>
                ))}
              </Select>
            </label>
            <div className="page-actions" style={{ justifyContent: "space-between" }}>
              <span className="thin">{activeTenantLabel}</span>
              <Button
                variant="ghost"
                type="button"
                onClick={async () => {
                  await signOut();
                  router.push("/login");
                }}
              >
                <LogOut size={16} />
                Sair
              </Button>
            </div>
          </Card>
        </aside>

        <div className="main-shell">
          <header className="header">
            <div className="header-left">
              <CurrentIcon size={20} />
              <div className="header-title">
                <div className="breadcrumbs" aria-label="Breadcrumb">
                  {breadcrumbs.map((crumb, index) => (
                    <span key={crumb.href} className="breadcrumb-item">
                      {index > 0 ? <span className="breadcrumb-separator">/</span> : null}
                      {crumb.current ? (
                        <strong>{crumb.label}</strong>
                      ) : (
                        <Link href={crumb.href as AppRoute}>{crumb.label}</Link>
                      )}
                    </span>
                  ))}
                </div>
                <strong>{route.title}</strong>
                <span>{route.description}</span>
              </div>
              <Button className="mobile-nav-trigger" variant="ghost" type="button" onClick={() => setMobileNavOpen(true)}>
                Menu
              </Button>
            </div>

            <div className="header-right">
              <Badge variant={health?.status === "healthy" ? "success" : "warning"}>
                {health?.status ?? "carregando"}
              </Badge>
              <Badge variant="info">
                <UserRound size={14} />
                {roleLabel}
              </Badge>
              <Badge variant="neutral">
                <Building2 size={14} />
                {activeWorkspaceLabel}
              </Badge>
              <Badge variant={health?.qdrant?.status === "ok" ? "info" : "danger"}>
                Qdrant {health?.qdrant?.status ?? "?"}
              </Badge>
              <Badge variant="neutral">
                {health?.timestamp ? formatDateTime(health.timestamp) : "aguardando health"}
              </Badge>
            </div>
          </header>

          <main className="content">
            {error ? (
              <div className="state-box">
                <h3>Healthcheck indisponível</h3>
                <p>{error}</p>
              </div>
            ) : null}
            {children}
          </main>
        </div>
      <Drawer open={mobileNavOpen} title="Navegação" onClose={() => setMobileNavOpen(false)}>
        <nav className="nav-group mobile-nav" aria-label="Navegação principal mobile">
          <div className="nav-group-title">Módulos</div>
          {navItems.map((item) => {
            const active = pathname === item.href;
            const Icon = ICONS[item.href] ?? ActivitySquare;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "nav-link active" : "nav-link"}
                aria-current={active ? "page" : undefined}
                onClick={() => setMobileNavOpen(false)}
              >
                <Icon size={18} />
                <span>
                  <strong>{item.label}</strong>
                  <br />
                  <small>{item.description}</small>
                </span>
              </Link>
            );
          })}
        </nav>
      </Drawer>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <EnterpriseSessionProvider>
      <ToastProvider>
        <Suspense
          fallback={
            <div className="auth-page">
              <div className="auth-shell auth-shell-single">
                <Card className="auth-panel">
                  <div className="state-box">
                    <h3>Preparando console</h3>
                    <p>Montando navegação, sessão e contexto do tenant ativo.</p>
                  </div>
                </Card>
              </div>
            </div>
          }
        >
          <AppShellFrame>{children}</AppShellFrame>
        </Suspense>
        <ToastViewport />
      </ToastProvider>
    </EnterpriseSessionProvider>
  );
}
