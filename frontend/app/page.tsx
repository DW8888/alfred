'use client';

import { useCallback, useEffect, useMemo, useState } from "react";

type PersonalInfo = {
  name?: string;
  location?: string;
  email?: string;
  phone?: string;
  links?: string[];
};

type Profile = {
  personal_info?: PersonalInfo;
  summary?: string;
  core_skills?: string[];
  [key: string]: unknown;
};

type Preferences = {
  target_title?: string;
  location?: string;
  results_per_page?: number | null;
  max_pages?: number | null;
};

type JobRecord = {
  id: number;
  title: string;
  company?: string;
  location?: string;
  description?: string;
  source_url?: string;
};

type MatchResult = {
  artifact_id?: number;
  name?: string;
  combined_score?: number;
  similarity?: number;
  snippet?: string;
  source?: string;
};

const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const MAX_VISIBLE_JOBS = 10;

export default function ControlPanelPage() {
  const [apiBaseInput, setApiBaseInput] = useState(DEFAULT_API_BASE);
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileFields, setProfileFields] = useState({
    name: "",
    location: "",
    email: "",
    phone: "",
    summary: "",
    coreSkills: "",
    linksText: "[]",
  });
  const [advancedMode, setAdvancedMode] = useState(false);
  const [advancedJson, setAdvancedJson] = useState("");
  const [preferences, setPreferences] = useState<Preferences>({
    target_title: "",
    location: "",
    results_per_page: null,
    max_pages: null,
  });
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [matches, setMatches] = useState<MatchResult[]>([]);
  const [consoleMessage, setConsoleMessage] = useState(
    "Select a job to view matches or generate documents.",
  );
  const [jobsLoading, setJobsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [expandedJobs, setExpandedJobs] = useState<Record<number, boolean>>({});

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

  const loadProfile = useCallback(async () => {
    if (!normalizedApiBase) {
      return;
    }
    setProfileLoading(true);
    try {
      const resp = await fetch(buildUrl("/profile/"));
      if (!resp.ok) {
        throw new Error("Failed to load profile");
      }
      const data: Profile = await resp.json();
      setProfile(data);
      const personal = data.personal_info ?? {};
      setProfileFields({
        name: personal.name ?? "",
        location: personal.location ?? "",
        email: personal.email ?? "",
        phone: personal.phone ?? "",
        summary: data.summary ?? "",
        coreSkills: (data.core_skills ?? []).join(", "),
        linksText: JSON.stringify(personal.links ?? [], null, 2),
      });
      if (!advancedMode) {
        setAdvancedJson(JSON.stringify(data, null, 2));
      }
    } catch (err) {
      setConsoleMessage(`Profile load error: ${err}`);
    } finally {
      setProfileLoading(false);
    }
  }, [advancedMode, buildUrl, normalizedApiBase]);

  const loadPreferences = useCallback(async () => {
    if (!normalizedApiBase) {
      return;
    }
    try {
      const resp = await fetch(buildUrl("/profile/preferences"));
      if (!resp.ok) {
        throw new Error("Failed to load preferences");
      }
      const data = await resp.json();
      setPreferences({
        target_title: data.target_title ?? "",
        location: data.location ?? "",
        results_per_page:
            typeof data.results_per_page === "number" ? data.results_per_page : null,
        max_pages: typeof data.max_pages === "number" ? data.max_pages : null,
      });
    } catch (err) {
      setConsoleMessage(`Preferences load error: ${err}`);
    }
  }, [buildUrl, normalizedApiBase]);

  const loadJobs = useCallback(async () => {
    if (!normalizedApiBase) {
      return;
    }
    setJobsLoading(true);
    setConsoleMessage("Refreshing jobs...");
    try {
      const resp = await fetch(buildUrl(`/jobs/?limit=${MAX_VISIBLE_JOBS}`));
      if (!resp.ok) {
        throw new Error("Failed to load jobs");
      }
      const data: JobRecord[] = await resp.json();
      setJobs(data);
      setConsoleMessage(`Loaded ${data.length} jobs.`);
    } catch (err) {
      setConsoleMessage(`Job load error: ${err}`);
    } finally {
      setJobsLoading(false);
    }
  }, [buildUrl, normalizedApiBase]);

  useEffect(() => {
    loadProfile();
    loadPreferences();
    loadJobs();
  }, [loadProfile, loadPreferences, loadJobs]);

  const handleApplyApiBase = () => {
    if (!apiBaseInput.trim()) {
      return;
    }
    const cleaned = apiBaseInput.trim().replace(/\/$/, "");
    setApiBase(cleaned);
    setConsoleMessage(`API base updated to ${cleaned}. Reloading data...`);
    setMatches([]);
  };

  const parseLinksInput = (): string[] => {
    try {
      const parsed = JSON.parse(profileFields.linksText || "[]");
      if (!Array.isArray(parsed)) {
        throw new Error("Links must be an array");
      }
      return parsed
        .map((entry) => String(entry).trim())
        .filter((entry) => entry.length > 0);
    } catch {
      throw new Error("Links must be a valid JSON array.");
    }
  };

  const handleProfileSave = async () => {
    if (!profile) {
      return;
    }
    let payload: Profile;
    if (advancedMode && advancedJson.trim()) {
      try {
        payload = JSON.parse(advancedJson) as Profile;
      } catch {
        setConsoleMessage("Profile save error: Invalid JSON in advanced editor.");
        return;
      }
    } else {
      try {
        payload = JSON.parse(JSON.stringify(profile ?? {})) as Profile;
        const links = parseLinksInput();
        payload.personal_info = {
          ...(payload.personal_info ?? {}),
          name: profileFields.name,
          location: profileFields.location,
          email: profileFields.email,
          phone: profileFields.phone,
          links,
        };
        payload.summary = profileFields.summary;
        payload.core_skills = profileFields.coreSkills
          .split(",")
          .map((s) => s.trim())
          .filter((s) => s.length > 0);
      } catch (err) {
        setConsoleMessage(`Profile save error: ${err}`);
        return;
      }
    }

    try {
      const resp = await fetch(buildUrl("/profile/"), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        throw new Error("Failed to save profile");
      }
      setProfile(payload);
      setAdvancedJson(JSON.stringify(payload, null, 2));
      setConsoleMessage("Profile saved.");
      loadProfile();
    } catch (err) {
      setConsoleMessage(`Profile save error: ${err}`);
    }
  };

  const handlePreferencesSave = async () => {
    try {
      if (
        preferences.results_per_page !== null &&
        preferences.results_per_page !== undefined &&
        preferences.results_per_page <= 0
      ) {
        throw new Error("Results per page must be greater than zero.");
      }
      if (
        preferences.max_pages !== null &&
        preferences.max_pages !== undefined &&
        preferences.max_pages <= 0
      ) {
        throw new Error("Max pages must be greater than zero.");
      }
      const resp = await fetch(buildUrl("/profile/preferences"), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(preferences),
      });
      if (!resp.ok) {
        throw new Error("Failed to save preferences");
      }
      setConsoleMessage("Preferences saved.");
    } catch (err) {
      setConsoleMessage(`Preferences save error: ${err}`);
    }
  };

  const handleFetchNewJobs = async () => {
    setConsoleMessage("Fetching new jobs...");
    try {
      const resp = await fetch(buildUrl("/jobs/fetch_jobs"), {
        method: "POST",
      });
      if (!resp.ok) {
        throw new Error("Fetch agent failed");
      }
      setConsoleMessage("Job fetcher finished.");
      await loadJobs();
    } catch (err) {
      setConsoleMessage(`Fetch jobs error: ${err}`);
    }
  };

  const buildJobPayload = (job: JobRecord) => ({
    job_id: job.id,
    title: job.title,
    company: job.company ?? "",
    description: job.description ?? "",
    top_k: 5,
  });

  const handleMatchJob = async (job: JobRecord) => {
    setActionLoading(true);
    setConsoleMessage("Fetching matches...");
    try {
      const resp = await fetch(buildUrl("/jobs/match"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildJobPayload(job)),
      });
      if (!resp.ok) {
        throw new Error("Match request failed");
      }
      const data = await resp.json();
      setMatches(data.matches ?? []);
      setConsoleMessage(
        `Found ${(data.matches ?? []).length} matches for "${job.title}".`,
      );
    } catch (err) {
      setConsoleMessage(`Match error: ${err}`);
      setMatches([]);
    } finally {
      setActionLoading(false);
    }
  };

  const handleGenerateDocument = async (
    job: JobRecord,
    kind: "resume" | "cover",
  ) => {
    setActionLoading(true);
    setConsoleMessage(
      `Generating ${kind === "resume" ? "resume" : "cover letter"}...`,
    );
    try {
      const endpoint =
        kind === "resume"
          ? "/jobs/generate_resume_job_focus"
          : "/jobs/generate_cover_letter";
      const resp = await fetch(buildUrl(endpoint), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildJobPayload(job)),
      });
      if (!resp.ok) {
        throw new Error("Generation failed");
      }
      const data = await resp.json();
      const reasoning = data.reasoning ? `Reasoning:\n${data.reasoning}\n\n` : "";
      const doc =
        data.generated_resume ??
        data.generated_cover_letter ??
        "No content returned.";
      const artifactLine = data.artifact_id
        ? `\n\nSaved artifact id: ${data.artifact_id}`
        : "";
      setConsoleMessage(`${reasoning}${doc}${artifactLine}`);
    } catch (err) {
      setConsoleMessage(`Generation error: ${err}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleAdvanced = () => {
    setAdvancedMode((prev) => {
      const next = !prev;
      if (next && profile) {
        setAdvancedJson(JSON.stringify(profile, null, 2));
      }
      return next;
    });
  };

  const toggleJobDetails = (jobId: number) => {
    setExpandedJobs((prev) => ({
      ...prev,
      [jobId]: !prev[jobId],
    }));
  };

  return (
    <>
      <header className="hero">
        <h1>Alfred Control Panel</h1>
        <p>Manage your profile, preferences, and job workflows.</p>
      </header>

      <main className="container">
        <div className="primary-column">
        <section className="card">
          <h2>API Endpoint</h2>
          <label htmlFor="api-base">Backend Base URL</label>
          <div className="card-actions">
            <input
              id="api-base"
              value={apiBaseInput}
              onChange={(e) => setApiBaseInput(e.target.value)}
              placeholder="http://127.0.0.1:8000"
            />
            <button className="btn" onClick={handleApplyApiBase}>
              Use URL
            </button>
          </div>
          <p className="muted">
            Current: <strong>{normalizedApiBase}</strong>
          </p>
        </section>

        <section className="card">
          <div className="section-header">
            <h2>Profile</h2>
            {profileLoading && <span className="muted">Loading...</span>}
          </div>
          <p>Edit immutable profile information. These fields feed every resume.</p>
          <div className="grid-two">
            <div>
              <label htmlFor="pf-name">Name</label>
              <input
                id="pf-name"
                value={profileFields.name}
                onChange={(e) =>
                  setProfileFields((prev) => ({ ...prev, name: e.target.value }))
                }
              />
            </div>
            <div>
              <label htmlFor="pf-location">Location</label>
              <input
                id="pf-location"
                value={profileFields.location}
                onChange={(e) =>
                  setProfileFields((prev) => ({
                    ...prev,
                    location: e.target.value,
                  }))
                }
              />
            </div>
          </div>
          <div className="grid-two">
            <div>
              <label htmlFor="pf-email">Email</label>
              <input
                id="pf-email"
                value={profileFields.email}
                onChange={(e) =>
                  setProfileFields((prev) => ({ ...prev, email: e.target.value }))
                }
              />
            </div>
            <div>
              <label htmlFor="pf-phone">Phone</label>
              <input
                id="pf-phone"
                value={profileFields.phone}
                onChange={(e) =>
                  setProfileFields((prev) => ({ ...prev, phone: e.target.value }))
                }
              />
            </div>
          </div>
          <label htmlFor="pf-links">Links (JSON array)</label>
          <textarea
            id="pf-links"
            value={profileFields.linksText}
            onChange={(e) =>
              setProfileFields((prev) => ({ ...prev, linksText: e.target.value }))
            }
            rows={3}
          />
          <label htmlFor="pf-summary">Summary</label>
          <textarea
            id="pf-summary"
            value={profileFields.summary}
            onChange={(e) =>
              setProfileFields((prev) => ({ ...prev, summary: e.target.value }))
            }
            rows={3}
          />
          <label htmlFor="pf-skills">Core Skills (comma separated)</label>
          <textarea
            id="pf-skills"
            value={profileFields.coreSkills}
            onChange={(e) =>
              setProfileFields((prev) => ({
                ...prev,
                coreSkills: e.target.value,
              }))
            }
            rows={2}
          />

          <div className="toggle-row">
            <input
              type="checkbox"
              id="advanced-toggle"
              checked={advancedMode}
              onChange={handleToggleAdvanced}
            />
            <label htmlFor="advanced-toggle">
              Enable advanced JSON editor (overrides form inputs)
            </label>
          </div>

          <label htmlFor="pf-json">Full Profile JSON</label>
          <textarea
            id="pf-json"
            value={advancedJson}
            onChange={(e) => setAdvancedJson(e.target.value)}
            rows={10}
            disabled={!advancedMode}
          />
          <small className="muted">
            Saving with advanced mode enabled overwrites the entire profile file.
          </small>
          <div className="card-actions">
            <button className="btn" onClick={handleProfileSave}>
              Save Profile
            </button>
            <button className="btn secondary" onClick={loadProfile}>
              Reload Profile
            </button>
          </div>
        </section>

        <section className="card">
          <h2>Job Preferences</h2>
          <div className="grid-two">
            <div>
              <label htmlFor="pref-title">Target Title</label>
              <input
                id="pref-title"
                value={preferences.target_title ?? ""}
                onChange={(e) =>
                  setPreferences((prev) => ({
                    ...prev,
                    target_title: e.target.value,
                  }))
                }
                placeholder="e.g. Senior Data Engineer"
              />
            </div>
            <div>
              <label htmlFor="pref-location">Preferred Location</label>
              <input
                id="pref-location"
                value={preferences.location ?? ""}
                onChange={(e) =>
                  setPreferences((prev) => ({
                    ...prev,
                    location: e.target.value,
                  }))
                }
                placeholder="e.g. New York, Remote"
              />
            </div>
            <div>
              <label htmlFor="pref-results">Results per Page</label>
              <input
                id="pref-results"
                type="number"
                min={1}
                value={preferences.results_per_page ?? ""}
                onChange={(e) =>
                  setPreferences((prev) => ({
                    ...prev,
                    results_per_page:
                      e.target.value === "" ? null : Number(e.target.value),
                  }))
                }
                placeholder="20"
              />
            </div>
            <div>
              <label htmlFor="pref-pages">Max Pages per Run</label>
              <input
                id="pref-pages"
                type="number"
                min={1}
                value={preferences.max_pages ?? ""}
                onChange={(e) =>
                  setPreferences((prev) => ({
                    ...prev,
                    max_pages: e.target.value === "" ? null : Number(e.target.value),
                  }))
                }
                placeholder="3"
              />
            </div>
          </div>
          <button className="btn" onClick={handlePreferencesSave}>
            Save Preferences
          </button>
        </section>

        <section className="card">
          <div className="section-header">
            <div>
              <h2>Job Board</h2>
              <p className="muted">Latest entries from Alfred backend.</p>
            </div>
            <div className="card-actions">
              <button
                className="btn secondary"
                onClick={() => {
                  void loadJobs();
                }}
              >
                {jobsLoading ? "Refreshing..." : "Refresh Jobs"}
              </button>
              <button className="btn" onClick={handleFetchNewJobs}>
                Fetch New Jobs
              </button>
            </div>
          </div>
          <div className="job-list">
            {jobsLoading && <p>Loading jobs...</p>}
            {!jobsLoading && jobs.length === 0 && <p>No jobs found.</p>}
            {!jobsLoading &&
              jobs.map((job) => (
                <article key={job.id} className="job-card">
                  <h3>{job.title}</h3>
                  <p>
                    <strong>Job ID:</strong> {job.id}
                  </p>
                  <p>
                    <strong>Company:</strong> {job.company || "n/a"}
                  </p>
                  <p>
                    <strong>Location:</strong> {job.location || "n/a"}
                  </p>
                  <p>
                    <strong>Description:</strong>{" "}
                    {expandedJobs[job.id]
                      ? job.description || "No description"
                      : `${(job.description ?? "").slice(0, 240) || "No description"}${
                          (job.description ?? "").length > 240 ? "..." : ""
                        }`}
                  </p>
                  {expandedJobs[job.id] && job.source_url && (
                    <p>
                      <strong>Job Link:</strong>{" "}
                      <a
                        href={job.source_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open posting
                      </a>
                    </p>
                  )}
                  <div className="job-actions">
                    <button
                      className="btn secondary"
                      onClick={() => toggleJobDetails(job.id)}
                    >
                      {expandedJobs[job.id] ? "Hide Details" : "View Details"}
                    </button>
                    <button
                      className="btn secondary"
                      onClick={() => handleMatchJob(job)}
                      disabled={actionLoading}
                    >
                      View Matches
                    </button>
                    <button
                      className="btn"
                      onClick={() => handleGenerateDocument(job, "resume")}
                      disabled={actionLoading}
                    >
                      Resume
                    </button>
                    <button
                      className="btn secondary"
                      onClick={() => handleGenerateDocument(job, "cover")}
                      disabled={actionLoading}
                    >
                      Cover Letter
                    </button>
                  </div>
                </article>
              ))}
          </div>
        </section>

        <section className="card">
          <h2>Job Matches</h2>
          {matches.length === 0 ? (
            <p className="muted">Matches will appear here after selecting a job.</p>
          ) : (
            <div className="matches-grid">
              {matches.map((match, idx) => (
                <div key={`${match.artifact_id ?? idx}-${idx}`} className="match-card">
                  <h3>{match.name || "Artifact"}</h3>
                  <p>
                    <strong>Source:</strong> {match.source || "n/a"}
                  </p>
                  <p>
                    <strong>Combined Score:</strong>{" "}
                    {(match.combined_score ?? 0).toFixed(3)}
                  </p>
                  <p>
                    <strong>Snippet:</strong> {match.snippet || "No snippet"}
                  </p>
                </div>
              ))}
            </div>
          )}
        </section>
        </div>

        <aside className="console-column">
          <section className="card">
            <h2>Result Console</h2>
            <pre className="console">{consoleMessage}</pre>
          </section>
        </aside>
      </main>
    </>
  );
}
