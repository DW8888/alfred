from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Debug UI"])


@router.get("/ui/test", response_class=HTMLResponse)
def tester_ui():
    """Simple in-app UI for testing matcher and resume endpoints."""

    html = """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8" />
        <title>Alfred Debug UI</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 2rem; background: #f5f7fa; }
            h1 { margin-bottom: 0.25rem; }
            .card { background: #fff; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
            label { display: block; font-weight: bold; margin-top: 0.75rem; }
            textarea, input { width: 100%; padding: 0.5rem; margin-top: 0.25rem; }
            button { margin-top: 1rem; padding: 0.6rem 1rem; border: none; border-radius: 4px;
                     background: #2563eb; color: #fff; cursor: pointer; }
            button:disabled { opacity: 0.6; cursor: not-allowed; }
            pre { background: #0d1117; color: #c9d1d9; padding: 1rem; border-radius: 6px;
                  max-height: 400px; overflow: auto; }
            .row { display: flex; gap: 1rem; flex-wrap: wrap; }
            .row > div { flex: 1; min-width: 280px; }
        </style>
    </head>
    <body>
        <h1>Alfred Debug UI</h1>
        <p>Use this page to hit <code>/jobs/match</code>, <code>/jobs/generate_resume</code>, and
        <code>/jobs/generate_cover_letter</code> without spinning up the orchestrator.</p>

        <div class="card">
            <div class="row">
                <div>
                    <label>Job Title</label>
                    <input type="text" id="title" placeholder="e.g. Data Engineer" />
                </div>
                <div>
                    <label>Company</label>
                    <input type="text" id="company" placeholder="Company name" />
                </div>
                <div>
                    <label>Top K Artifacts</label>
                    <input type="number" id="top_k" min="1" max="20" value="5" />
                </div>
            </div>
            <label>Job Description</label>
            <textarea id="description" rows="8" placeholder="Paste job description here"></textarea>

            <div>
                <button onclick="callEndpoint('match')" id="matchBtn">Run Matcher</button>
                <button onclick="callEndpoint('resume')" id="resumeBtn">Generate Resume</button>
                <button onclick="callEndpoint('cover')" id="coverBtn">Generate Cover Letter</button>
            </div>
        </div>

        <div class="card">
            <h2>Response</h2>
            <pre id="output">Awaiting response...</pre>
        </div>

        <script>
            const output = document.getElementById("output");

            function payload() {
                return {
                    title: document.getElementById("title").value || "",
                    company: document.getElementById("company").value || "",
                    description: document.getElementById("description").value || "",
                    top_k: Number(document.getElementById("top_k").value) || 5
                };
            }

            function setLoading(isLoading) {
                document.getElementById("matchBtn").disabled = isLoading;
                document.getElementById("resumeBtn").disabled = isLoading;
                document.getElementById("coverBtn").disabled = isLoading;
            }

            async function callEndpoint(kind) {
                const body = payload();
                if (!body.description.trim()) {
                    output.textContent = "Please provide a job description.";
                    return;
                }

                let url = "/jobs/match";
                if (kind === "resume") url = "/jobs/generate_resume";
                if (kind === "cover") url = "/jobs/generate_cover_letter";

                setLoading(true);
                output.textContent = "Loading...";

                try {
                    const resp = await fetch(url, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(body)
                    });

                    const data = await resp.json();
                    output.textContent = JSON.stringify(data, null, 2);
                } catch (err) {
                    output.textContent = "Request failed: " + err;
                } finally {
                    setLoading(false);
                }
            }
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html)
