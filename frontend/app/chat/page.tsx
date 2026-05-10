"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Copy, MessageSquareText } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { ROUTE_META } from "@/lib/navigation";
import { formatMillis, formatPercent, truncate } from "@/lib/utils";
import { loadStoredJson, saveStoredJson } from "@/lib/storage";
import { PageHeader } from "@/components/layout/page-header";
import { useEnterpriseSession } from "@/components/layout/enterprise-session-provider";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Select, Skeleton, Tabs, Textarea, useToast } from "@/components/ui";
import type { QueryResponse, RetrievalProfile } from "@/types";

const FORM_STORAGE_KEY = "frontend.chat.form.v2";
const HISTORY_STORAGE_KEY = "frontend.chat.history";

type ChatFormState = {
  query: string;
  workspaceId: string;
  topK: number;
  threshold: number;
  retrievalProfile: RetrievalProfile | "";
};

type ChatHistoryEntry = {
  id: string;
  query: string;
  createdAt: string;
  result: QueryResponse;
};

const DEFAULT_FORM: ChatFormState = {
  query: "",
  workspaceId: "default",
  topK: 5,
  threshold: 0.25,
  retrievalProfile: "clinical_v2",
};

function answerText(response: QueryResponse) {
  return response.answer_markdown || response.answer;
}

function canViewRetrievalDebug(role?: string) {
  return role === "super_admin" || role === "admin_rag" || role === "admin";
}

function sanitizeRetrievalDebug(retrieval: QueryResponse["retrieval"] | null | undefined) {
  if (!retrieval) {
    return {};
  }
  const raw = retrieval as Record<string, unknown>;
  const scores = (raw.scores_breakdown ?? {}) as Record<string, unknown>;
  const evidencePack = (raw.clinical_evidence_pack ?? {}) as Record<string, unknown>;
  const sections = (evidencePack.sections ?? {}) as Record<string, Record<string, unknown>>;

  return {
    workspace_id: raw.workspace_id,
    method: raw.method,
    retrieval_profile: raw.retrieval_profile,
    total_candidates: raw.total_candidates,
    low_confidence: raw.low_confidence,
    retrieval_low_confidence: raw.retrieval_low_confidence,
    retrieval_time_ms: raw.retrieval_time_ms,
    results_count: Array.isArray(raw.results) ? raw.results.length : 0,
    clinical_fanout: scores.clinical_fanout,
    clinical_scope_filter: summarizeScopeFilter(scores.clinical_scope_filter),
    clinical_reranking: scores.clinical_reranking,
    clinical_generation: raw.clinical_generation,
    clinical_evidence_pack: {
      source_method: evidencePack.source_method,
      total_items: evidencePack.total_items,
      missing_sections: evidencePack.missing_sections,
      section_order: evidencePack.section_order,
      bibliography_count: Array.isArray(evidencePack.bibliography) ? evidencePack.bibliography.length : 0,
      sections: Object.fromEntries(
        Object.entries(sections).map(([key, section]) => [
          key,
          {
            status: section.status,
            item_count: Array.isArray(section.items) ? section.items.length : 0,
            bibliography_count: Array.isArray(section.bibliography) ? section.bibliography.length : 0,
          },
        ]),
      ),
    },
  };
}

function AnswerMarkdown({ value }: { value: string }) {
  const blocks = value
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  return (
    <div className="clinical-answer professor-answer">
      {blocks.map((block, index) => {
        if (block.startsWith("## ")) {
          const [heading, ...rest] = block.split("\n");
          return (
            <section key={`${heading}-${index}`} className="clinical-section">
              <div className="clinical-section-title">
                <strong>{heading.replace(/^##\s+/, "")}</strong>
              </div>
              {rest.length ? <AnswerMarkdown value={rest.join("\n")} /> : null}
            </section>
          );
        }

        const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
        const isList = lines.length > 1 && lines.every((line) => /^(-|\d+\.)\s+/.test(line));
        if (isList) {
          return (
            <ul key={`list-${index}`} className="answer-list">
              {lines.map((line) => (
                <li key={line}>{line.replace(/^(-|\d+\.)\s+/, "")}</li>
              ))}
            </ul>
          );
        }

        return <p key={`paragraph-${index}`}>{block}</p>;
      })}
    </div>
  );
}

function summarizeScopeFilter(value: unknown) {
  const scope = (value ?? {}) as Record<string, unknown>;
  const removedChunks = Array.isArray(scope.removed_chunks) ? scope.removed_chunks : [];
  return {
    applied: scope.applied,
    kept_count: scope.kept_count,
    removed_count: scope.removed_count,
    removed_reasons: removedChunks.map((chunk) => {
      const item = chunk as Record<string, unknown>;
      return {
        chunk_id: item.chunk_id,
        reason: item.reason,
        score: item.score,
        primary_clinical_category: item.primary_clinical_category,
      };
    }),
  };
}

export default function ChatPage() {
  const { pushToast } = useToast();
  const { session } = useEnterpriseSession();
  const activeWorkspaceId = session?.active_tenant.workspace_id ?? "default";
  const allowRetrievalDebug = canViewRetrievalDebug(session?.user.role);
  const [form, setForm] = useState<ChatFormState>(DEFAULT_FORM);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [history, setHistory] = useState<ChatHistoryEntry[]>([]);

  useEffect(() => {
    setForm({ ...DEFAULT_FORM, ...loadStoredJson<ChatFormState>(FORM_STORAGE_KEY, DEFAULT_FORM) });
    setHistory(loadStoredJson<ChatHistoryEntry[]>(HISTORY_STORAGE_KEY, []));
  }, []);

  useEffect(() => {
    setForm((current) => ({ ...current, workspaceId: activeWorkspaceId }));
  }, [activeWorkspaceId]);

  useEffect(() => {
    saveStoredJson(FORM_STORAGE_KEY, form);
  }, [form]);

  useEffect(() => {
    saveStoredJson(HISTORY_STORAGE_KEY, history.slice(0, 12));
  }, [history]);

  async function submitChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.query({
        query: form.query,
        workspace_id: activeWorkspaceId,
        top_k: form.topK,
        threshold: form.threshold,
        stream: false,
        model: null,
        retrieval_profile: form.retrievalProfile || null,
      });
      setResult(response);
      setHistory((current) => [
        {
          id: `${Date.now()}`,
          query: form.query,
          createdAt: new Date().toISOString(),
          result: response,
        },
        ...current,
      ].slice(0, 12));
      pushToast({
        title: "Resposta gerada",
        description: `Confiança ${response.confidence} · grounding ${response.grounded ? "sim" : "não"}.`,
        intent: response.grounded ? "success" : "info",
      });
      setForm((current) => ({ ...current, query: "" }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Falha ao consultar o chat");
    } finally {
      setLoading(false);
    }
  }

  async function copyAnswer(answer: string) {
    try {
      await navigator.clipboard.writeText(answer);
      pushToast({ title: "Resposta copiada", description: "O conteúdo foi enviado para a área de transferência.", intent: "success" });
    } catch {
      pushToast({ title: "Cópia indisponível", description: "Não foi possível copiar a resposta.", intent: "error" });
    }
  }

  return (
    <div className="page stack">
      <PageHeader
        eyebrow={ROUTE_META["/chat"].eyebrow}
        title={ROUTE_META["/chat"].title}
        description={ROUTE_META["/chat"].description}
      />

      <Card className="card-inner">
        <form className="form-grid" onSubmit={submitChat}>
          <label className="ui-label">
            Pergunta
            <Textarea
              value={form.query}
              onChange={(event) => setForm((current) => ({ ...current, query: event.target.value }))}
              placeholder="Pergunte algo ao corpus"
            />
          </label>
          <div className="grid cols-4">
            <label className="ui-label">
              Workspace
              <Input
                value={form.workspaceId}
                readOnly
                placeholder={activeWorkspaceId}
              />
            </label>
            <label className="ui-label">
              Top K
              <Input
                type="number"
                min={1}
                max={20}
                value={form.topK}
                onChange={(event) => setForm((current) => ({ ...current, topK: Number(event.target.value) || 5 }))}
              />
            </label>
            <label className="ui-label">
              Threshold
              <Input
                type="number"
                step="0.05"
                min={0}
                max={1}
                value={form.threshold}
                onChange={(event) => setForm((current) => ({ ...current, threshold: Number(event.target.value) || 0.25 }))}
              />
            </label>
            <label className="ui-label">
              Retrieval
              <Select
                value={form.retrievalProfile}
                onChange={(event) => setForm((current) => ({ ...current, retrievalProfile: event.target.value as RetrievalProfile | "" }))}
              >
                <option value="">Padrão do sistema</option>
                <option value="clinical_v2">clinical_v2</option>
                <option value="hybrid">hybrid</option>
                <option value="hyde_hybrid">hyde_hybrid</option>
                <option value="semantic_hybrid">semantic_hybrid</option>
                <option value="semantic_hyde_hybrid">semantic_hyde_hybrid</option>
              </Select>
            </label>
          </div>
          <div className="page-actions">
            {form.retrievalProfile ? <Badge variant="neutral">{form.retrievalProfile}</Badge> : null}
            <Button type="submit" disabled={loading}>
              <MessageSquareText size={16} />
              {loading ? "Gerando..." : "Gerar resposta"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setHistory([]);
                setResult(null);
                setError(null);
              }}
            >
              Limpar sessão
            </Button>
          </div>
        </form>
      </Card>

      {error ? <ErrorState title="Chat indisponível" description={error} /> : null}

      {!loading && !result && !error ? (
        <EmptyState title="Nenhuma resposta ainda" description="Envie uma pergunta para carregar a resposta com grounding." />
      ) : null}

      {loading ? <Skeleton className="skeleton" /> : null}

      {result ? (
        <div className="grid cols-2">
          <Card className="card-inner">
            <div className="card-header">
              <div className="card-title">
                <strong>Resposta</strong>
                <span>{result.confidence}</span>
              </div>
              <div className="page-actions" style={{ gap: 8 }}>
                <Badge variant={result.grounded ? "success" : "warning"}>{result.grounded ? "grounded" : "sem grounding"}</Badge>
                <Badge variant={result.low_confidence ? "danger" : "info"}>{result.low_confidence ? "baixa confiança" : "confiante"}</Badge>
                {result.grounding?.needs_review ? <Badge variant="warning">needs review</Badge> : null}
                {result.guardrails?.unsupported_claims?.length ? <Badge variant="danger">claims sem suporte</Badge> : null}
              </div>
            </div>
            <AnswerMarkdown value={answerText(result)} />
            <p className="thin">
              Citação: {formatPercent(result.citation_coverage, 0)} · Latência {formatMillis(result.latency_ms)}
            </p>
            {result.retrieval_profile ? <p className="thin">Retrieval profile: {result.retrieval_profile}</p> : null}
            <div className="page-actions">
              <Button variant="secondary" onClick={() => void copyAnswer(answerText(result))}>
                <Copy size={16} />
                Copiar resposta
              </Button>
            </div>
          </Card>

          <Card className="card-inner">
            <Tabs
              items={[
                {
                  value: "citations",
                  label: "Citações",
                  content: (
                    <div className="list">
                      {result.citations.length ? (
                        result.citations.map((citation) => (
                          <div key={citation.chunk_id} className="list-item">
                            <strong>{citation.document_filename ?? citation.document_id}</strong>
                            <p className="thin">{truncate(citation.text, 240)}</p>
                            <p className="thin mono">{citation.chunk_id}</p>
                          </div>
                        ))
                      ) : (
                        <EmptyState title="Sem citações" description="A resposta não trouxe citações estruturadas." />
                      )}
                    </div>
                  ),
                },
                {
                  value: "references",
                  label: "Referências",
                  content: (
                    <div className="list">
                      {result.bibliography?.length ? (
                        result.bibliography.map((reference) => (
                          <div key={`${reference.document_filename}-${reference.page}-${reference.chunk_id}`} className="list-item">
                            <strong>{reference.document_filename ?? reference.document_id ?? "Documento sem nome"}</strong>
                            <p className="thin">{reference.page != null ? `p. ${reference.page}` : "p. n/a"} · {reference.sections.join(", ") || "seção não informada"}</p>
                            <p className="thin mono">{reference.chunk_id}</p>
                          </div>
                        ))
                      ) : (
                        <EmptyState title="Sem referências" description="A resposta não trouxe rodapé bibliográfico estruturado." />
                      )}
                    </div>
                  ),
                },
                {
                  value: "retrieval",
                  label: "Retrieval",
                  content: allowRetrievalDebug ? (
                    <pre className="mono">{JSON.stringify(sanitizeRetrievalDebug(result.retrieval), null, 2)}</pre>
                  ) : (
                    <EmptyState title="Debug restrito" description="Diagnóstico de retrieval disponível apenas para perfis administrativos." />
                  ),
                },
              ]}
            />
          </Card>
        </div>
      ) : null}

      <Card className="card-inner">
        <div className="card-header">
          <div className="card-title">
            <strong>Sessão atual</strong>
            <span>Histórico local persistido no navegador.</span>
          </div>
          <Badge variant="info">{history.length} interações</Badge>
        </div>
        {history.length ? (
          <div className="timeline">
            {history.map((entry) => (
              <div key={entry.id} className="timeline-item">
                <div className="card-header">
                  <div className="card-title">
                    <strong>{entry.query}</strong>
                    <span>{new Date(entry.createdAt).toLocaleString("pt-BR")}</span>
                  </div>
                  <div className="page-actions" style={{ gap: 8 }}>
                    <Badge variant={entry.result.grounded ? "success" : "warning"}>{entry.result.confidence}</Badge>
                    {entry.result.low_confidence ? <Badge variant="danger">low confidence</Badge> : null}
                  </div>
                </div>
                <p>{truncate(answerText(entry.result), 320)}</p>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="Sessão vazia" description="As respostas recentes do chat aparecerão aqui para manter contexto operacional." />
        )}
      </Card>
    </div>
  );
}
