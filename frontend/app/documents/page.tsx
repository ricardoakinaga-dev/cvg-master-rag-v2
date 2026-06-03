"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { loadStoredJson, saveStoredJson } from "@/lib/storage";
import { ROUTE_META } from "@/lib/navigation";
import { formatDateTime, formatNumber, humanFileSize, truncate } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { useEnterpriseSession } from "@/components/layout/enterprise-session-provider";
import {
  Badge,
  Button,
  Card,
  Drawer,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  Select,
  Skeleton,
  Table,
  useToast,
} from "@/components/ui";
import type { DocumentIngestionJobStatus, DocumentListItem, DocumentListResponse, DocumentMetadata } from "@/types";
import { Upload, RefreshCcw, ChevronLeft, ChevronRight, FileUp } from "lucide-react";

type Filters = {
  workspace_id: string;
  query: string;
  source_type: string;
  status: string;
};

type UploadFeedback = {
  intent: "success" | "error";
  title: string;
  description: string;
};

const ACTIVE_JOB_STATUSES = new Set<DocumentIngestionJobStatus["status"]>(["pending", "processing"]);
const FILTERS_STORAGE_KEY = "frontend.documents.filters";
const COLLECTION_STORAGE_KEY = "frontend.documents.qdrant_collection";
const DEFAULT_QDRANT_COLLECTION = "cvg_master_rag";
const COLLECTION_NAME_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
const NEW_COLLECTION_VALUE = "__new_collection__";

export default function DocumentsPage() {
  const { pushToast } = useToast();
  const { session } = useEnterpriseSession();
  const activeWorkspaceId = session?.active_tenant.workspace_id ?? "default";
  const previousJobStatuses = useRef<Record<string, DocumentIngestionJobStatus["status"]>>({});
  const [filters, setFilters] = useState<Filters>({ workspace_id: activeWorkspaceId, query: "", source_type: "", status: "" });
  const [appliedFilters, setAppliedFilters] = useState<Filters>(filters);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [data, setData] = useState<DocumentListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState<DocumentListItem | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<DocumentMetadata | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploadFeedback, setUploadFeedback] = useState<UploadFeedback | null>(null);
  const [ingestionJobs, setIngestionJobs] = useState<DocumentIngestionJobStatus[]>([]);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [jobsLastUpdatedAt, setJobsLastUpdatedAt] = useState<string | null>(null);
  const [qdrantCollection, setQdrantCollection] = useState(DEFAULT_QDRANT_COLLECTION);
  const [qdrantCollections, setQdrantCollections] = useState<string[]>([DEFAULT_QDRANT_COLLECTION]);
  const [collectionsError, setCollectionsError] = useState<string | null>(null);

  useEffect(() => {
    const stored = loadStoredJson<Filters>(FILTERS_STORAGE_KEY, {
      workspace_id: activeWorkspaceId,
      query: "",
      source_type: "",
      status: "",
    });
    setFilters(stored);
    setAppliedFilters(stored);
  }, [activeWorkspaceId]);

  useEffect(() => {
    setFilters((current) => ({ ...current, workspace_id: activeWorkspaceId }));
    setAppliedFilters((current) => ({ ...current, workspace_id: activeWorkspaceId }));
  }, [activeWorkspaceId]);

  useEffect(() => {
    saveStoredJson(FILTERS_STORAGE_KEY, filters);
  }, [filters]);

  useEffect(() => {
    const stored = loadStoredJson<string>(COLLECTION_STORAGE_KEY, DEFAULT_QDRANT_COLLECTION);
    setQdrantCollection(stored || DEFAULT_QDRANT_COLLECTION);
  }, []);

  useEffect(() => {
    saveStoredJson(COLLECTION_STORAGE_KEY, qdrantCollection);
  }, [qdrantCollection]);

  useEffect(() => {
    let active = true;
    api.documents
      .listQdrantCollections(activeWorkspaceId)
      .then((response) => {
        if (!active) return;
        const next = Array.from(new Set([response.active_collection, DEFAULT_QDRANT_COLLECTION, ...response.collections])).sort();
        setQdrantCollections(next);
        setQdrantCollection((current) => current || response.active_collection || DEFAULT_QDRANT_COLLECTION);
        setCollectionsError(null);
      })
      .catch((err: unknown) => {
        if (!active) return;
        const detail = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Falha ao carregar coleções";
        setCollectionsError(detail);
      });
    return () => {
      active = false;
    };
  }, [activeWorkspaceId]);

  const refreshIngestionJobs = useCallback(async () => {
    try {
      const response = await api.documents.listIngestionJobs(activeWorkspaceId, 6);
      setIngestionJobs(response.items);
      setJobsError(null);
      setJobsLastUpdatedAt(new Date().toISOString());
    } catch (err: unknown) {
      const detail = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Falha ao carregar jobs";
      setJobsError(`Atualização atrasada: ${detail}`);
    }
  }, [activeWorkspaceId]);

  useEffect(() => {
    let active = true;
    async function loadJobs() {
      try {
        const response = await api.documents.listIngestionJobs(activeWorkspaceId, 6);
        if (!active) return;
        setIngestionJobs(response.items);
        setJobsError(null);
        setJobsLastUpdatedAt(new Date().toISOString());
      } catch (err: unknown) {
        if (!active) return;
        const detail = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Falha ao carregar jobs";
        setJobsError(`Atualização atrasada: ${detail}`);
      }
    }

    void loadJobs();
    const interval = window.setInterval(loadJobs, 5000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [activeWorkspaceId]);

  useEffect(() => {
    const previous = previousJobStatuses.current;
    const finishedNow = ingestionJobs.some((job) => {
      const priorStatus = previous[job.ingestion_id];
      return priorStatus && ACTIVE_JOB_STATUSES.has(priorStatus) && !ACTIVE_JOB_STATUSES.has(job.status);
    });
    previousJobStatuses.current = Object.fromEntries(
      ingestionJobs.map((job) => [job.ingestion_id, job.status]),
    );
    if (finishedNow) {
      setPage(0);
      setAppliedFilters((current) => ({ ...current }));
    }
  }, [ingestionJobs]);

  useEffect(() => {
    let active = true;
    if (!selected) {
      setSelectedDetail(null);
      setDetailError(null);
      return () => {
        active = false;
      };
    }

    setDetailLoading(true);
    setDetailError(null);
    api.documents
      .get(selected.document_id, selected.workspace_id)
      .then((response) => {
        if (active) setSelectedDetail(response);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setDetailError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Falha ao carregar metadata");
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });

    return () => {
      active = false;
    };
  }, [selected]);

  const summary = useMemo(() => {
    const items = data?.items ?? [];
    return {
      total: data?.total ?? 0,
      parsed: items.filter((item) => item.status === "parsed").length,
      partial: items.filter((item) => item.status !== "parsed").length,
      chunks: items.reduce((sum, item) => sum + item.chunk_count, 0),
    };
  }, [data]);
  const collectionIsValid = COLLECTION_NAME_PATTERN.test(qdrantCollection.trim());
  const collectionSelectValue = qdrantCollections.includes(qdrantCollection) ? qdrantCollection : NEW_COLLECTION_VALUE;

  function handleCollectionChoice(value: string) {
    if (value === NEW_COLLECTION_VALUE) {
      setQdrantCollection("");
      return;
    }
    setQdrantCollection(value);
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    api.documents
      .list(activeWorkspaceId, {
        limit: pageSize,
        offset: page * pageSize,
        query: appliedFilters.query || undefined,
        source_type: appliedFilters.source_type || undefined,
        status: appliedFilters.status || undefined,
      })
      .then((response) => {
        if (active) setData(response);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Falha ao carregar documentos");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [activeWorkspaceId, appliedFilters, page, pageSize]);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setUploading(true);
    setUploadFeedback(null);
    const targetCollection = qdrantCollection.trim();
    if (!COLLECTION_NAME_PATTERN.test(targetCollection)) {
      const description = "Use 1 a 64 caracteres: letras, números, _ ou -.";
      setUploading(false);
      setUploadFeedback({ intent: "error", title: "Coleção Qdrant inválida", description });
      pushToast({ title: "Coleção Qdrant inválida", description, intent: "error" });
      return;
    }
    try {
      const workspaceId = activeWorkspaceId;
      const uploadedFileName = file.name;
      const result = await api.documents.upload(file, workspaceId, targetCollection);
      const queued = result.status === "queued";
      const description = queued
        ? `${uploadedFileName} foi recebido e será indexado em ${targetCollection}.`
        : `${uploadedFileName} foi incorporado ao corpus de ${workspaceId} em ${result.qdrant_collection ?? targetCollection}.`;
      setUploadFeedback({
        intent: "success",
        title: queued ? "Indexação em fila" : "Documento enviado",
        description,
      });
      setShowUpload(false);
      setFile(null);
      pushToast({
        title: queued ? "Upload recebido" : "Upload concluído",
        description,
        intent: "success",
      });
      void refreshIngestionJobs();
      setQdrantCollections((current) => Array.from(new Set([...current, targetCollection])).sort());
      setPage(0);
      setAppliedFilters({ ...filters, workspace_id: workspaceId });
    } catch (err) {
      const description = err instanceof Error ? err.message : "Não foi possível enviar o arquivo";
      pushToast({
        title: "Falha no upload",
        description,
        intent: "error",
      });
      setUploadFeedback({
        intent: "error",
        title: "Falha no upload",
        description,
      });
    } finally {
      setUploading(false);
    }
  }

  function applyFilters() {
    setPage(0);
    setAppliedFilters({ ...filters, workspace_id: activeWorkspaceId });
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  }

  function jobBadgeVariant(status: DocumentIngestionJobStatus["status"]) {
    if (status === "committed") return "success";
    if (status === "failed" || status === "aborted") return "danger";
    if (status === "processing") return "info";
    return "warning";
  }

  function operationalBadgeVariant(status?: DocumentIngestionJobStatus["operational_status"] | null) {
    if (status === "completed") return "success";
    if (status === "failed" || status === "stalled") return "danger";
    if (status === "warning") return "warning";
    if (status === "running") return "info";
    return "neutral";
  }

  function jobProgress(job: DocumentIngestionJobStatus) {
    if (!job.page_count) return null;
    return Math.min(100, Math.max(0, Math.round((job.pages_processed / job.page_count) * 100)));
  }

  function formatRate(value?: number | null, label = "min") {
    if (value === null || value === undefined || Number.isNaN(value)) return "taxa —";
    return `${formatNumber(Math.round(value))}/${label}`;
  }

  function formatStaleness(seconds?: number | null) {
    if (seconds === null || seconds === undefined) return "lote —";
    if (seconds < 60) return `${formatNumber(seconds)}s sem lote`;
    return `${formatNumber(Math.floor(seconds / 60))}min sem lote`;
  }

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize));
  const currentPage = Math.min(page + 1, totalPages);

  return (
    <div className="page stack">
      <PageHeader
        eyebrow={ROUTE_META["/documents"].eyebrow}
        title={ROUTE_META["/documents"].title}
        description={ROUTE_META["/documents"].description}
        actions={
          <>
            <Button variant="secondary" onClick={() => setShowUpload(true)}>
              <Upload size={16} />
              Upload
            </Button>
            <Button variant="ghost" onClick={applyFilters}>
              <RefreshCcw size={16} />
              Atualizar
            </Button>
          </>
        }
      />

      <div className="grid cols-4">
        <Card className="card-inner">
          <div className="card-title">
            <strong>Total</strong>
            <span>Documentos listados</span>
          </div>
          <div className="metric">{loading ? <Skeleton className="skeleton-inline" /> : formatNumber(summary.total)}</div>
        </Card>
        <Card className="card-inner">
          <div className="card-title">
            <strong>Parsed</strong>
            <span>Prontos para busca</span>
          </div>
          <div className="metric">{loading ? <Skeleton className="skeleton-inline" /> : formatNumber(summary.parsed)}</div>
        </Card>
        <Card className="card-inner">
          <div className="card-title">
            <strong>Parciais</strong>
            <span>Precisa revisão</span>
          </div>
          <div className="metric">{loading ? <Skeleton className="skeleton-inline" /> : formatNumber(summary.partial)}</div>
        </Card>
        <Card className="card-inner">
          <div className="card-title">
            <strong>Chunks</strong>
            <span>Soma do catálogo</span>
          </div>
          <div className="metric">{loading ? <Skeleton className="skeleton-inline" /> : formatNumber(summary.chunks)}</div>
        </Card>
      </div>

      <Card className="card-inner">
        <div className="form-grid">
          <div className={collectionSelectValue === NEW_COLLECTION_VALUE ? "grid cols-5" : "grid cols-4"}>
            <label className="ui-label">
              Coleção Qdrant
              <Select
                value={collectionSelectValue}
                onChange={(event) => handleCollectionChoice(event.target.value)}
              >
                {qdrantCollections.map((collection) => (
                  <option value={collection} key={collection}>{collection}</option>
                ))}
                <option value={NEW_COLLECTION_VALUE}>Nova coleção</option>
              </Select>
            </label>
            {collectionSelectValue === NEW_COLLECTION_VALUE ? (
              <label className="ui-label">
                Nome da nova coleção
                <Input
                  value={qdrantCollection}
                  onChange={(event) => setQdrantCollection(event.target.value.trim())}
                  placeholder="ex: gestacao_de_cadelas"
                />
              </label>
            ) : null}
            <label className="ui-label">
              Busca
              <Input
                value={filters.query}
                onChange={(event) => setFilters((current) => ({ ...current, query: event.target.value }))}
                placeholder="filtrar por nome, ID ou tag"
              />
            </label>
            <label className="ui-label">
              Tipo
              <Select value={filters.source_type} onChange={(event) => setFilters((current) => ({ ...current, source_type: event.target.value }))}>
                <option value="">Todos</option>
                <option value="pdf">pdf</option>
                <option value="docx">docx</option>
                <option value="md">md</option>
                <option value="txt">txt</option>
                <option value="unknown">unknown</option>
              </Select>
            </label>
            <label className="ui-label">
              Status
              <Select value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}>
                <option value="">Todos</option>
                <option value="parsed">parsed</option>
                <option value="partial">partial</option>
                <option value="failed">failed</option>
              </Select>
            </label>
          </div>

          <div className="page-actions">
            <Button variant="primary" onClick={applyFilters}>
              Aplicar filtros
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                const cleared = { workspace_id: "default", query: "", source_type: "", status: "" };
                setFilters(cleared);
                setPage(0);
                setAppliedFilters(cleared);
              }}
            >
              Limpar
            </Button>
            <label className="ui-label" style={{ minWidth: 160 }}>
              Itens por página
              <Select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value) || 10)}>
                <option value={5}>5</option>
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
              </Select>
            </label>
          </div>
        </div>
      </Card>

      {error ? <ErrorState title="Falha ao carregar documentos" description={error} /> : null}

      {uploadFeedback ? (
        <Card className="card-inner">
          <div className="card-title">
            <strong>{uploadFeedback.title}</strong>
            <span>{uploadFeedback.description}</span>
          </div>
          <Badge variant={uploadFeedback.intent === "success" ? "success" : "danger"}>
            {uploadFeedback.intent === "success" ? "status ok" : "verificar"}
          </Badge>
        </Card>
      ) : null}

      {ingestionJobs.length || jobsError ? (
        <Card className="card-inner">
          <div className="card-title">
            <strong>Indexações</strong>
            <span>{jobsError ?? `${formatNumber(ingestionJobs.length)} indexações recentes`}</span>
          </div>
          {jobsError ? (
            <div className="state-box">
              <h3>Status temporariamente atrasado</h3>
              <p>{jobsError}</p>
              {jobsLastUpdatedAt ? <p>Última atualização válida: {formatDateTime(jobsLastUpdatedAt)}</p> : null}
            </div>
          ) : null}
          {ingestionJobs.length ? (
            <div className="job-list">
              {ingestionJobs.map((job) => {
                const progress = jobProgress(job);
                const primaryAlert = job.operational_alerts?.[0];
                return (
                  <div className="job-row" key={job.ingestion_id}>
                    <div className="job-row-main">
                      <div>
                        <strong>{job.filename}</strong>
                        <div className="thin mono">{truncate(job.ingestion_id, 24)}</div>
                      </div>
                      <div className="page-actions">
                        <Badge variant={jobBadgeVariant(job.status)}>{job.status}</Badge>
                        <Badge variant={operationalBadgeVariant(job.operational_status)}>{job.operational_status ?? "status —"}</Badge>
                      </div>
                    </div>
                    <div className="job-progress-track" aria-label={`Progresso de ${job.filename}`}>
                      <div className="job-progress-fill" style={{ width: `${progress ?? 0}%` }} />
                    </div>
                    <div className="job-grid">
                      <span>{formatNumber(job.pages_processed)} / {formatNumber(job.page_count)} páginas</span>
                      <span>{formatNumber(job.chunks_written)} chunks</span>
                      <span>{formatNumber(job.qdrant_points_written)} pontos</span>
                      <span>{job.rss_peak_mb ? `${formatNumber(Math.round(job.rss_peak_mb))} MB RSS` : "RSS —"}</span>
                      <span>{job.file_size_bytes ? humanFileSize(job.file_size_bytes) : "tamanho —"}</span>
                      <span>{job.resource_isolation_mode ?? "isolamento —"}</span>
                      <span>{job.qdrant_collection ?? DEFAULT_QDRANT_COLLECTION}</span>
                      <span>{formatRate(job.pages_per_minute, "min")} páginas</span>
                      <span>{formatRate(job.chunks_per_minute, "min")} chunks</span>
                      <span>{formatStaleness(job.seconds_since_last_batch)}</span>
                      <span>heartbeat {formatDateTime(job.last_heartbeat_at)}</span>
                    </div>
                    {primaryAlert ? <div className="thin">{primaryAlert.code}: {primaryAlert.message}</div> : null}
                    {job.error_message ? <div className="thin">{job.error_code}: {job.error_message}</div> : null}
                  </div>
                );
              })}
            </div>
          ) : null}
        </Card>
      ) : null}

      {!loading && !error && (data?.items?.length ?? 0) === 0 ? (
        <EmptyState
          title="Nenhum documento encontrado"
          description="A listagem está vazia para os filtros atuais."
        />
      ) : null}

      <Card className="card-inner">
        <Table>
          <thead>
            <tr>
              <th>Documento</th>
              <th>Origem</th>
              <th>Escopo</th>
              <th>Coleção</th>
              <th>Status</th>
              <th>Páginas</th>
              <th>Chunks</th>
              <th>Criado</th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 4 }).map((_, index) => (
                  <tr key={index}>
                    <td colSpan={8}>
                      <Skeleton className="skeleton" />
                    </td>
                  </tr>
                ))
              : data?.items?.map((item) => (
                  <tr key={item.document_id} onClick={() => setSelected(item)} style={{ cursor: "pointer" }}>
                    <td>
                      <strong>{item.filename}</strong>
                      <div className="thin mono">{truncate(item.document_id, 24)}</div>
                    </td>
                    <td>{item.source_type}</td>
                    <td>
                      <Badge variant={item.catalog_scope === "canonical" ? "info" : "warning"}>
                        {item.catalog_scope}
                      </Badge>
                    </td>
                    <td>
                      <span className="code-chip">{item.qdrant_collection ?? DEFAULT_QDRANT_COLLECTION}</span>
                    </td>
                    <td>
                      <Badge
                        variant={item.status === "parsed" ? "success" : item.status === "partial" ? "warning" : "danger"}
                      >
                        {item.status}
                      </Badge>
                    </td>
                    <td>{item.page_count ?? "—"}</td>
                    <td>{item.chunk_count}</td>
                    <td>{formatDateTime(item.created_at)}</td>
                  </tr>
                ))}
          </tbody>
        </Table>
        <div className="page-actions" style={{ justifyContent: "space-between", marginTop: 16 }}>
          <div className="thin">
            Página {currentPage} de {totalPages} · {formatNumber(data?.total ?? 0)} documentos
          </div>
          <div className="page-actions">
            <Button variant="ghost" disabled={page === 0 || loading} onClick={() => setPage((current) => Math.max(0, current - 1))}>
              <ChevronLeft size={16} />
              Anterior
            </Button>
            <Button
              variant="ghost"
              disabled={page + 1 >= totalPages || loading}
              onClick={() => setPage((current) => Math.min(totalPages - 1, current + 1))}
            >
              Próxima
              <ChevronRight size={16} />
            </Button>
          </div>
        </div>
      </Card>

      <Drawer open={Boolean(selected)} title={selected?.filename ?? "Documento"} onClose={() => setSelected(null)}>
        {selected ? (
          <>
            {detailLoading ? <Skeleton className="skeleton" /> : null}
            {detailError ? <ErrorState title="Falha ao carregar metadata" description={detailError} /> : null}
            {selectedDetail ? (
              <div className="list">
                <div className="list-item">
                  <strong>ID</strong>
                  <p className="thin mono">{selectedDetail.document_id}</p>
                </div>
                <div className="list-item">
                  <strong>Filename</strong>
                  <p className="thin">{selectedDetail.filename}</p>
                </div>
                <div className="list-item">
                  <strong>Escopo</strong>
                  <p className="thin">{selectedDetail.catalog_scope}</p>
                </div>
                <div className="list-item">
                  <strong>Source type</strong>
                  <p className="thin">{selectedDetail.source_type}</p>
                </div>
                <div className="list-item">
                  <strong>Chunks</strong>
                  <p className="thin">{selectedDetail.chunk_count}</p>
                </div>
                <div className="list-item">
                  <strong>Criado</strong>
                  <p className="thin">{formatDateTime(selectedDetail.created_at)}</p>
                </div>
                <div className="list-item">
                  <strong>Indexado</strong>
                  <p className="thin">{formatDateTime(selectedDetail.indexed_at)}</p>
                </div>
                <div className="list-item">
                  <strong>Embeddings</strong>
                  <p className="thin">{selectedDetail.embeddings_model ?? "—"}</p>
                </div>
                <div className="list-item">
                  <strong>Coleção Qdrant</strong>
                  <p className="thin mono">{selectedDetail.qdrant_collection ?? DEFAULT_QDRANT_COLLECTION}</p>
                </div>
                <div className="list-item">
                  <strong>Tags</strong>
                  <p className="thin">{selectedDetail.tags?.length ? selectedDetail.tags.join(", ") : "—"}</p>
                </div>
                <div className="list-item">
                  <strong>Metadata</strong>
                  <p className="thin">
                    {selectedDetail.char_count} caracteres · {selectedDetail.chunk_count} chunks · {selectedDetail.chunking_strategy}
                  </p>
                </div>
                <div className="list-item">
                  <strong>Ações</strong>
                  <p className="thin">Reprocessamento ainda não está disponível via backend.</p>
                  <Button variant="ghost" disabled>
                    Reprocessar
                  </Button>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </Drawer>

      <Modal open={showUpload} title="Upload de documento" onClose={() => setShowUpload(false)}>
        <form className="form-grid" onSubmit={handleUpload}>
          <div className={collectionSelectValue === NEW_COLLECTION_VALUE ? "grid cols-2" : "grid"}>
            <label className="ui-label">
              Coleção Qdrant
              <Select
                value={collectionSelectValue}
                onChange={(event) => handleCollectionChoice(event.target.value)}
              >
                {qdrantCollections.map((collection) => (
                  <option value={collection} key={collection}>{collection}</option>
                ))}
                <option value={NEW_COLLECTION_VALUE}>Nova coleção</option>
              </Select>
            </label>
            {collectionSelectValue === NEW_COLLECTION_VALUE ? (
              <label className="ui-label">
                Nome da nova coleção
                <Input
                  value={qdrantCollection}
                  onChange={(event) => setQdrantCollection(event.target.value.trim())}
                  placeholder="ex: gestacao_de_cadelas"
                />
              </label>
            ) : null}
          </div>
          {collectionsError ? (
            <div className="state-box">
              <h3>Coleções indisponíveis</h3>
              <p>{collectionsError}</p>
            </div>
          ) : null}
          <div
            className={dragging ? "state-box drag-active" : "state-box"}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
          >
            <h3>Arraste e solte</h3>
            <p>Solte um arquivo PDF, DOCX, MD ou TXT aqui, ou escolha manualmente abaixo.</p>
          </div>
          <label className="ui-label">
            Arquivo
            <Input
              type="file"
              accept=".pdf,.docx,.md,.txt"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          {file ? (
            <div className="list-item">
              <strong>{file.name}</strong>
              <p className="thin">{formatNumber(Math.round(file.size / 1024))} KB · pronto para upload</p>
            </div>
          ) : null}
          <div className="page-actions">
            <Button type="submit" disabled={!file || uploading || !collectionIsValid}>
              {uploading ? "Enviando..." : "Enviar"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setShowUpload(false)}>
              Cancelar
            </Button>
            <Badge variant="neutral">
              <FileUp size={14} />
              Upload web
            </Badge>
          </div>
        </form>
      </Modal>
    </div>
  );
}
