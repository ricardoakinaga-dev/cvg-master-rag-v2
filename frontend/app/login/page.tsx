"use client";

import type { Route } from "next";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { ArrowRight, LogIn } from "lucide-react";
import { useEnterpriseSession } from "@/components/layout/enterprise-session-provider";
import { Button, Card, Input, Select, useToast } from "@/components/ui";

function LoginContent() {
  const router = useRouter();
  const { pushToast } = useToast();
  const { session, signIn } = useEnterpriseSession();
  const tenants = session?.available_tenants ?? [];
  const [role, setRole] = useState<"super_admin" | "admin_rag" | "auditor" | "operator" | "viewer">("super_admin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantId, setTenantId] = useState(session?.active_tenant.tenant_id ?? "default");
  const [loading, setLoading] = useState(false);
  const [nextPath, setNextPath] = useState("/");

  useEffect(() => {
    if (!session) return;
    setTenantId(session.active_tenant.tenant_id);
  }, [session]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const next = new URLSearchParams(window.location.search).get("next");
    setNextPath(next && next.startsWith("/") ? next : "/");
  }, []);

  useEffect(() => {
    if (!session?.authenticated || session.session_state !== "active") return;
    router.replace(nextPath as Route);
  }, [nextPath, router, session]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    try {
      await signIn({
        email: email.trim(),
        password,
        tenant_id: tenantId,
      });
      setEmail("");
      setPassword("");
      pushToast({
        title: "Sessão carregada",
        description: "Você entrou no console enterprise com contexto de tenant.",
        intent: "success",
      });
      router.replace(nextPath as Route);
    } catch (error) {
      pushToast({
        title: "Falha no login",
        description: error instanceof Error ? error.message : "Não foi possível abrir a sessão",
        intent: "error",
      });
      setPassword("");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-shell auth-shell-single">
        <Card className="auth-panel">
          <form className="form-grid" onSubmit={handleSubmit} autoComplete="off">
            <div className="card-title">
              <strong>Entrar no console</strong>
              <span>Informe manualmente e-mail, senha e tenant.</span>
            </div>

            <div className="grid cols-1">
              <label className="ui-label">
                Perfil
                <Select
                  value={role}
                  onChange={(event) => {
                    const nextRole = event.target.value as typeof role;
                    setRole(nextRole);
                  }}
                  autoComplete="off"
                >
                  <option value="super_admin">super_admin</option>
                  <option value="admin_rag">admin_rag</option>
                  <option value="auditor">auditor</option>
                  <option value="operator">operator</option>
                  <option value="viewer">viewer</option>
                </Select>
              </label>

              <label className="ui-label">
                E-mail
                <Input
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="Digite seu e-mail"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                />
              </label>

              <label className="ui-label">
                Senha
                <Input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Digite sua senha"
                  autoComplete="current-password"
                />
              </label>

              <label className="ui-label">
                Tenant
                <Select
                  value={tenantId}
                  onChange={(event) => setTenantId(event.target.value)}
                  disabled={!tenants.length}
                  autoComplete="off"
                >
                  {tenants.length ? (
                    tenants.map((tenant) => (
                      <option key={tenant.tenant_id} value={tenant.tenant_id}>
                        {tenant.name} · {tenant.workspace_id}
                      </option>
                    ))
                  ) : (
                    <option value={tenantId}>Carregando tenants...</option>
                  )}
                </Select>
              </label>
            </div>

            <div className="auth-actions">
              <Button type="submit" disabled={loading}>
                <LogIn size={16} />
                {loading ? "Entrando..." : "Entrar"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => router.push("/onboarding")}>
                Próximo passo
                <ArrowRight size={16} />
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="auth-page">
          <div className="auth-shell auth-shell-single">
            <Card className="auth-panel">
              <div className="state-box">
                <h3>Carregando login</h3>
                <p>Preparando sessão enterprise.</p>
              </div>
            </Card>
          </div>
        </div>
      }
    >
      <LoginContent />
    </Suspense>
  );
}
