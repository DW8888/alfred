'use client';

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type PersonaResumeSummary = {
  variant: string;
  job_id: number;
  artifact_id?: number | null;
  reasoning_preview?: string;
  filename?: string;
  updated_at?: number;
};

type PersonaResumeDetail = PersonaResumeSummary & {
  reasoning?: string;
  resume_markdown?: string;
};

const DEFAULT_API_BASE = "http://127.0.0.1:8000";

export default function PersonaViewerPage() {
  const [apiBaseInput, setApiBaseInput] = useState(DEFAULT_API_BASE);
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [personaSummaries, setPersonaSummaries] = useState<PersonaResumeSummary[]>([]);
  const [selectedVariant, setSelectedVariant] = useState("");
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [personaDetail, setPersonaDetail] = useState<PersonaResumeDetail | null>(null);
  const [statusMessage, setStatusMessage] = useState("Select a persona to view its resume markdown.");
  const [listLoading, setListLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  const normalizedApiBase = useMemo(
    () => apiBase.replace(/\/$/, ""),
    [apiBase],
  );

  const buildUrl = useCallback(
    (path: string) => `${normalizedApiBase}${path}`,
    [normalizedApiBase],
  );

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const stored = window.localStorage.getItem("alfredApiBase");
    if (stored) {
      setApiBase(stored);
      setApiBaseInput(stored);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("alfredApiBase", normalizedApiBase);
  }, [normalizedApiBase]);

  const handleApplyApiBase = () => {
    if (!apiBaseInput.trim()) {
      return;
    }
    const cleaned = apiBaseInput.trim().replace(/\/$/, "");
    setApiBase(cleaned);
    setStatusMessage(`API base updated to ${cleaned}. Reloading data...`);
    void loadPersonaResumes(cleaned);
  };

  const loadPersonaResumes = useCallback(
    async (customBase?: string) => {
      const baseToUse = customBase ? customBase.replace(/\/$/, "") : normalizedApiBase;
      if (!baseToUse) {
        return;
      }
      setListLoading(true);
      try {
        const resp = await fetch(`${baseToUse}/persona_resumes/`);
        if (!resp.ok) {
          throw new Error("Failed to load persona resumes");
        }
        const data: PersonaResumeSummary[] = await resp.json();
        data.sort((a, b) => {
          if (a.variant === b.variant) {
            return a.job_id - b.job_id;
          }
          return a.variant.localeCompare(b.variant);
        });
        setPersonaSummaries(data);
        if (data.length === 0) {
          setSelectedVariant("");
          setSelectedJobId(null);
          setPersonaDetail(null);
          setStatusMessage("No persona resumes found on disk.");
          return;
        }
        const availableVariants = Array.from(new Set(data.map((entry) => entry.variant)));
        setSelectedVariant((prev) => {
          if (prev && availableVariants.includes(prev)) {
            return prev;
          }
          return availableVariants[0];
        });
        setStatusMessage(`Loaded ${data.length} persona resume summaries.`);
      } catch (err) {
        setPersonaSummaries([]);
        setSelectedVariant("");
        setSelectedJobId(null);
        setPersonaDetail(null);
        setStatusMessage(`Persona load error: ${err}`);
      } finally {
        setListLoading(false);
      }
    },
    [normalizedApiBase],
  );

  const fetchPersonaDetail = useCallback(
    async (variant: string, jobId: number) => {
      setDetailLoading(true);
      try {
        const resp = await fetch(buildUrl(`/persona_resumes/${variant}/${jobId}`));
        if (!resp.ok) {
          throw new Error("Failed to load persona resume");
        }
        const data: PersonaResumeDetail = await resp.json();
        setPersonaDetail(data);
        setStatusMessage(`Loaded persona ${variant} resume for job ${jobId}.`);
      } catch (err) {
        setStatusMessage(`Persona resume error: ${err}`);
        setPersonaDetail(null);
      } finally {
        setDetailLoading(false);
      }
    },
    [buildUrl],
  );

  useEffect(() => {
    void loadPersonaResumes();
  }, [loadPersonaResumes]);

  useEffect(() => {
    if (!selectedVariant) {
      return;
    }
    if (!personaSummaries.some((entry) => entry.variant === selectedVariant)) {
      setSelectedVariant("");
      setSelectedJobId(null);
      setPersonaDetail(null);
    }
  }, [personaSummaries, selectedVariant]);

  useEffect(() => {
    if (!selectedVariant) {
      setSelectedJobId(null);
      setPersonaDetail(null);
      return;
    }
    const filtered = personaSummaries.filter((entry) => entry.variant === selectedVariant);
    if (!filtered.length) {
      setSelectedJobId(null);
      setPersonaDetail(null);
      return;
    }
    if (selectedJobId !== null && !filtered.some((entry) => entry.job_id === selectedJobId)) {
      setSelectedJobId(null);
      setPersonaDetail(null);
    }
  }, [personaSummaries, selectedVariant, selectedJobId]);

  useEffect(() => {
    if (!selectedVariant || selectedJobId === null) {
      setPersonaDetail(null);
      return;
    }
    void fetchPersonaDetail(selectedVariant, selectedJobId);
  }, [selectedVariant, selectedJobId, fetchPersonaDetail]);

  const filteredSummaries = selectedVariant
    ? personaSummaries.filter((entry) => entry.variant === selectedVariant)
    : [];

  return (
    <>
      <header className="hero hero-banner">
        <h1>Persona Resume Viewer</h1>
        <p>Inspect persona-specific resume outputs stored under prompt runs.</p>
      </header>

      <main className="container">
        <div className="primary-column">
          <section className="card">
            <div className="section-header">
              <h2>API Endpoint</h2>
              <Link className="btn secondary" href="/">
                Back to Control Panel
              </Link>
            </div>
            <label htmlFor="persona-api-base">Backend Base URL</label>
            <div className="card-actions">
              <input
                id="persona-api-base"
                value={apiBaseInput}
                onChange={(e) => setApiBaseInput(e.target.value)}
                placeholder="http://127.0.0.1:8000"
              />
              <button className="btn" onClick={handleApplyApiBase}>
                Use URL
              </button>
              <button
                className="btn secondary"
                onClick={() => {
                  void loadPersonaResumes();
                }}
              >
                {listLoading ? "Refreshing..." : "Refresh Data"}
              </button>
            </div>
            <p className="muted">
              Current: <strong>{normalizedApiBase}</strong>
            </p>
          </section>

          <section className="card">
            <div className="section-header">
              <h2>Persona Browser</h2>
              <span className="muted">
                {filteredSummaries.length} entries for {selectedVariant || "—"}
              </span>
            </div>
            <label htmlFor="variant-select">Persona Variant</label>
            <select
              id="variant-select"
              value={selectedVariant}
              onChange={(e) => {
                setSelectedVariant(e.target.value);
                setSelectedJobId(null);
                setPersonaDetail(null);
              }}
              disabled={listLoading || !personaSummaries.length}
            >
              <option value="" disabled>
                -- Select a persona variant --
              </option>
              {Array.from(new Set(personaSummaries.map((entry) => entry.variant))).map(
                (variant) => (
                  <option key={variant} value={variant}>
                    {variant}
                  </option>
                ),
              )}
            </select>

            <div className="persona-wrapper">
              <div className="persona-list">
                {!selectedVariant && (
                  <p className="muted">Select a persona variant to view runs.</p>
                )}
                {selectedVariant && listLoading && (
                  <p className="muted">Loading personas...</p>
                )}
                {selectedVariant && !listLoading && filteredSummaries.length === 0 && (
                  <p className="muted">No runs for this variant.</p>
                )}
                {selectedVariant &&
                  !listLoading &&
                  filteredSummaries.map((summary) => (
                    <button
                      key={`${summary.variant}-${summary.job_id}`}
                      className={`persona-item${
                        selectedJobId === summary.job_id ? " active" : ""
                      }`}
                      onClick={() => setSelectedJobId(summary.job_id)}
                      disabled={detailLoading && selectedJobId === summary.job_id}
                    >
                      <div className="persona-item-header">
                        <span className="persona-variant">{summary.variant}</span>
                        <span className="persona-job">Job #{summary.job_id}</span>
                      </div>
                      <p className="persona-preview-text">
                        {summary.reasoning_preview || "No reasoning snippet"}
                      </p>
                    </button>
                  ))}
              </div>
              <div className="persona-preview">
                {!selectedVariant && (
                  <p className="muted">Select a persona variant to begin.</p>
                )}
                {selectedVariant && detailLoading && (
                  <p className="muted">Loading markdown...</p>
                )}
                {selectedVariant && !detailLoading && !personaDetail && (
                  <p className="muted">Select a persona entry to display markdown.</p>
                )}
                {selectedVariant && !detailLoading && personaDetail && (
                  <>
                    <div className="persona-meta">
                      <p>
                        <strong>Variant:</strong> {personaDetail.variant}
                      </p>
                      <p>
                        <strong>Job ID:</strong> {personaDetail.job_id}
                      </p>
                      {personaDetail.artifact_id && (
                        <p>
                          <strong>Artifact ID:</strong> {personaDetail.artifact_id}
                        </p>
                      )}
                      {personaDetail.reasoning && (
                        <details>
                          <summary>Reasoning</summary>
                          <p>{personaDetail.reasoning}</p>
                        </details>
                      )}
                    </div>
                    <pre className="markdown-preview">
                      {personaDetail.resume_markdown || "No resume markdown found."}
                    </pre>
                  </>
                )}
              </div>
            </div>
          </section>
        </div>

        <aside className="console-column">
          <section className="card">
            <h2>Status</h2>
            <pre className="console">{statusMessage}</pre>
          </section>
        </aside>
      </main>
    </>
  );
}
