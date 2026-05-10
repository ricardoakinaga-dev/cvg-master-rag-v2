"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { ROUTE_META } from "@/lib/navigation";
import { formatMillis, formatNumber, formatPercent, truncate } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { useEnterpriseSession } from "@/components/layout/enterprise-session-provider";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Select, Skeleton, Tabs, Textarea, useToast } from "@/components/ui";
import { loadStoredJson, saveStoredJson } from "@/lib/storage";
import type { DocumentListItem, RetrievalProfile, SearchResponse, SearchResultItem } from "@/types";

const STORAGE_KEY = "frontend.search.state.v2";

type SearchFormState = {
  query: string;
  workspaceId: string;
  topK: number;
  threshold: number;
  retrievalProfile: RetrievalProfile | "";
  sourceType: string;
  documentId: string;
  tagsText: string;
  pageHintMin: string;
  pageHintMax: string;
};

const DEFAULT_STATE: SearchFormState = {
  query: "",
  workspaceId: "default",
  topK: 5,
  threshold: 0.25,
  retrievalProfile: "",
  sourceType: "",
  documentId: "",
  tagsText: "",
  pageHintMin: "",
  pageHintMax: "",
};

function highlightText(text: string, query: string) {
  const terms = query
    .toLowerCase()
    .split(/\s+/)
    .map((term) => term.trim())
    .filter((term) => term.length >= 3);

  if (!terms.length) return text;

  const pattern = new RegExp(`(${terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "ig");
  const parts = text.split(pattern);
  return parts.map((part, index) =>
    index % 2 === 1 ? (
      <mark key={`${part}-${index}`} className="text-highlight">
        {part}
      </mark>
    ) : (
      <span key={`${part}-${index}`}>{part}</span>
    ),
  );
}

export default function SearchPage() {
  const { pushToast } = useToast();
  const { session } = useEnterpriseSession();
  const activeWorkspaceId = session?.active_tenant.workspace_id ?? "default";
  const [form, setForm] = useState<SearchFormState>(DEFAULT_STATE);
  const [loading, setLoading] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null);

  useEffect(() => {
    const stored = loadStoredJson<SearchFormState>(STORAGE_KEY, DEFAULT_STATE);
    setForm({ ...DEFAULT_STATE, ...stored, workspaceId: stored.workspaceId || activeWorkspaceId });
  }, [activeWorkspaceId]);

  useEffect(() => {
    setForm((current) => ({ ...current, workspaceId: activeWorkspaceId }));
  }, [activeWorkspaceId]);

  useEffect(() => {
    saveStoredJson(STORAGE_KEY, form);
  }, [form]);

  useEffect(() => {
    let active = true;
    setCatalogLoading(true);
    api.documents
      .list(activeWorkspaceId, { limit: 200, offset: 0 })
      .then((response) => {
        if (active) setDocuments(response.items);
      })
      .catch(() => {
        if (active) setDocuments([]);
      })
      .finally(() => {
        if (active) setCatalogLoading(false);
      });
    return () => {
      active = false;
    };
  }, [activeWorkspaceId]);

  const availableTags = useMemo(() => {
    return Array.from(
      new Set(
        documents.flatMap((item) => item.tags ?? []).filter(Boolean),
      ),
    ).sort((a, b) => a.localeCompare(b));
  }, [documents]);

  const requestedTags = useMemo(() => {
    return form.tagsText
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
  }, [form.tagsText]);

  const selectedResult = useMemo<SearchResultItem | null>(() => {
    if (!result?.results.length) return null;
    return result.results.find((item) => item.chunk_id === selectedChunkId) ?? result.results[0];
  }, [result, selectedChunkId]);

  async function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const filters = {
        ...(form.sourceType ? { source_type: form.sourceType } : {}),
        ...(form.documentId ? { document_id: form.documentId } : {}),
        ...(requestedTags.length ? { tags: requestedTags } : {}),
        ...(form.pageHintMin !== "" ? { page_hint_min: Number(form.pageHintMin) } : {}),
        ...(form.pageHintMax !== "" ? { page_hint_max: Number(form.pageHintMax) } : {}),
      };
      const response = await api.search({
        query: form.query,
        workspace_id: activeWorkspaceId,
        top_k: form.topK,
        threshold: form.threshold,
        filters: Object.keys(filters).length ? filters : null,
        include_raw_scores: true,
        retrieval_profile: form.retrievalProfile || null,
      });
      setResult(response);
      setSelectedChunkId(response.results[0]?.chunk_id ?? null);
      pushToast({
        title: "Busca concluída",
        description: `${response.results.length} resultados encontrados.`,
        intent: response.low_confidence ? "info" : "success",
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Falha na busca");
    } finally {
      setLoading(false);
    }
  }

  const summary = result
    ? [
        { label: "Resultados", value: formatNumber(result.results.length) },
        { label: "Candidatos", value: formatNumber(result.total_candidates) },
        { label: "Tempo", value: formatMillis(result.retrieval_time_ms) },
        { label: "Baixa confiança", value: result.low_confidence ? "sim" : "não" },
      ]
    : [];

  return (
    <div className="page stack">
      <PageHeader
        eyebrow={ROUTE_META["/search"].eyebrow}
        title={ROUTE_META["/search"].title}
        description={ROUTE_META["/search"].description}
      />

      <Card className="card-inner">
        <form className="form-grid" onSubmit={runSearch}>
          <label className="ui-label">
            Pergunta
            <Textarea
              value={form.query}
              onChange={(event) => setForm((current) => ({ ...current, query: event.target.value }))}
              placeholder="Faça uma busca no corpus"
            />
          </label>
          <div className="grid cols-5">
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
                <option value="hybrid">hybrid</option>
                <option value="hyde_hybrid">hyde_hybrid</option>
                <option value="semantic_hybrid">semantic_hybrid</option>
                <option value="semantic_hyde_hybrid">semantic_hyde_hybrid</option>
              </Select>
            </label>
            <label className="ui-label">
              Origem
              <Select
                value={form.sourceType}
                onChange={(event) => setForm((current) => ({ ...current, sourceType: event.target.value }))}
              >
                <option value="">Todas</option>
                <option value="pdf">pdf</option>
                <option value="docx">docx</option>
                <option value="md">md</option>
                <option value="txt">txt</option>
              </Select>
            </label>
          </div>
          <div className="grid cols-4">
            <label className="ui-label">
              Documento
              <Select
                value={form.documentId}
                onChange={(event) => setForm((current) => ({ ...current, documentId: event.target.value }))}
              >
                <option value="">Todos</option>
                {documents.map((document) => (
                  <option key={document.document_id} value={document.document_id}>
                    {document.filename}
                  </option>
                ))}
              </Select>
            </label>
            <label className="ui-label">
              Tags
              <Input
                value={form.tagsText}
                onChange={(event) => setForm((current) => ({ ...current, tagsText: event.target.value }))}
                placeholder={availableTags.length ? availableTags.join(", ") : "tag1, tag2"}
              />
            </label>
            <label className="ui-label">
              Página mínima
              <Input
                type="number"
                min={0}
                value={form.pageHintMin}
                onChange={(event) => setForm((current) => ({ ...current, pageHintMin: event.target.value }))}
              />
            </label>
            <label className="ui-label">
              Página máxima
              <Input
                type="number"
                min={0}
                value={form.pageHintMax}
                onChange={(event) => setForm((current) => ({ ...current, pageHintMax: event.target.value }))}
              />
            </label>
          </div>
          <div className="page-actions">
            {catalogLoading ? <Badge variant="neutral">catálogo carregando</Badge> : <Badge variant="info">{documents.length} docs no catálogo</Badge>}
            {requestedTags.length ? <Badge variant="warning">{requestedTags.length} tags ativas</Badge> : null}
            {form.documentId ? <Badge variant="success">filtro por documento</Badge> : null}
            {form.retrievalProfile ? <Badge variant="neutral">{form.retrievalProfile}</Badge> : null}
          </div>
          <div className="page-actions">
            <Button type="submit" disabled={loading}>
              <Search size={16} />
              {loading ? "Buscando..." : "Executar busca"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setForm(DEFAULT_STATE);
                setResult(null);
                setSelectedChunkId(null);
                setError(null);
              }}
            >
              Limpar busca
            </Button>
          </div>
        </form>
      </Card>

      {error ? <ErrorState title="Busca indisponível" description={error} /> : null}

      {result ? (
        <div className="grid cols-4">
          {summary.map((item) => (
            <Card key={item.label} className="card-inner">
              <div className="card-title">
                <strong>{item.label}</strong>
                <span>{item.value}</span>
              </div>
            </Card>
          ))}
        </div>
      ) : null}

      {!loading && result && result.results.length === 0 ? (
        <EmptyState title="Sem resultados" description="A busca não retornou resultados para a consulta atual." />
      ) : null}

      <div className="split">
        <div className="stack">
          {loading ? <Skeleton className="skeleton" /> : null}
          {result?.results.map((item) => (
            <button
              key={item.chunk_id}
              type="button"
              className={selectedChunkId === item.chunk_id ? "card card-inner card-clickable active" : "card card-inner card-clickable"}
              onClick={() => setSelectedChunkId(item.chunk_id)}
            >
              <div className="card-header">
                <div className="card-title">
                  <strong>{item.document_filename ?? item.document_id}</strong>
                  <span>{truncate(item.text, 220)}</span>
                </div>
                <div className="stack" style={{ gap: 8 }}>
                  <Badge variant={item.score >= form.threshold ? "success" : "warning"}>score {item.score.toFixed(3)}</Badge>
                  <Badge variant="neutral">{item.source}</Badge>
                </div>
              </div>
              <div className="chip-row">
                <span className="code-chip">{item.document_id}</span>
                <span className="code-chip">{item.page_hint !== null ? `p.${item.page_hint}` : "sem página"}</span>
                {item.source_type ? <span className="code-chip">{item.source_type}</span> : null}
                {item.tags?.length ? <span className="code-chip">{item.tags.join(", ")}</span> : null}
              </div>
            </button>
          ))}
        </div>

        <Card className="card-inner sticky-panel">
          <div className="card-header">
            <div className="card-title">
              <strong>Detalhe da evidência</strong>
              <span>{selectedResult ? "Inspeção do chunk selecionado" : "Selecione um resultado"}</span>
            </div>
            {selectedResult ? <Badge variant="info">{selectedResult.score.toFixed(3)}</Badge> : null}
          </div>

          {selectedResult ? (
            <div className="stack">
              <div className="chip-row">
                <span className="code-chip">{selectedResult.document_filename ?? selectedResult.document_id}</span>
                <span className="code-chip">{selectedResult.chunk_id}</span>
                <span className="code-chip">{selectedResult.page_hint !== null ? `página ${selectedResult.page_hint}` : "sem página"}</span>
                {selectedResult.source_type ? <span className="code-chip">{selectedResult.source_type}</span> : null}
                {selectedResult.tags?.length ? <span className="code-chip">{selectedResult.tags.join(", ")}</span> : null}
              </div>
              <p>{highlightText(selectedResult.text, form.query)}</p>
              {result?.scores_breakdown ? (
                <div className="grid cols-2">
                  {Object.entries(result.scores_breakdown).map(([label, value]) => (
                    <div key={label} className="list-item">
                      <strong>{label}</strong>
                      <p className="thin">{typeof value === "number" ? value.toFixed(4) : String(value)}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="Sem breakdown" description="Ative raw scores para inspecionar a fusão e a confiança do ranking." />
              )}
            </div>
          ) : (
            <EmptyState title="Nenhum resultado selecionado" description="Execute uma busca e clique em um resultado para abrir o detalhe." />
          )}
        </Card>
      </div>

      {result ? (
        <Card className="card-inner">
          <Tabs
            items={[
              {
                value: "summary",
                label: "Resumo",
                content: (
                  <div className="list">
                    <div className="list-item">
                      <strong>Query</strong>
                      <p className="thin">{result.query}</p>
                    </div>
                    <div className="list-item">
                      <strong>Confiança</strong>
                      <p className="thin">{formatPercent(result.low_confidence ? 0 : 1, 0)} de confiança operacional.</p>
                    </div>
                    <div className="list-item">
                      <strong>Filtros ativos</strong>
                      <p className="thin">
                        {[
                          form.sourceType ? `origem=${form.sourceType}` : null,
                          form.documentId ? `documento=${form.documentId}` : null,
                          requestedTags.length ? `tags=${requestedTags.join(", ")}` : null,
                          form.pageHintMin !== "" ? `page_min=${form.pageHintMin}` : null,
                          form.pageHintMax !== "" ? `page_max=${form.pageHintMax}` : null,
                          result.retrieval_profile ? `retrieval=${result.retrieval_profile}` : null,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "sem filtros adicionais"}
                      </p>
                    </div>
                  </div>
                ),
              },
              {
                value: "raw",
                label: "Raw JSON",
                content: <pre className="mono">{JSON.stringify(result, null, 2)}</pre>,
              },
            ]}
          />
        </Card>
      ) : null}
    </div>
  );
}
