HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>cloudag &mdash; Declarative JSON DAG Workflow Studio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0a0d14;
      --bg-card: rgba(18, 24, 38, 0.85);
      --bg-card-hover: rgba(26, 35, 54, 0.95);
      --bg-input: #0e1320;
      --border-color: rgba(255, 255, 255, 0.08);
      --border-glow: rgba(99, 102, 241, 0.35);
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --accent-primary: #6366f1;
      --accent-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%);
      --accent-blue: #38bdf8;
      --accent-emerald: #10b981;
      --accent-amber: #f59e0b;
      --accent-rose: #f43f5e;
      --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
      --font-mono: 'Fira Code', monospace;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-dark);
      background-image: 
        radial-gradient(circle at 15% 15%, rgba(99, 102, 241, 0.12) 0%, transparent 40%),
        radial-gradient(circle at 85% 85%, rgba(168, 85, 247, 0.10) 0%, transparent 45%);
      color: var(--text-main);
      font-family: var(--font-sans);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
    }

    /* Header */
    header {
      backdrop-filter: blur(16px);
      background: rgba(10, 13, 20, 0.8);
      border-bottom: 1px solid var(--border-color);
      padding: 1rem 2rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 50;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .brand-icon {
      width: 36px;
      height: 36px;
      border-radius: 10px;
      background: var(--accent-gradient);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 20px rgba(99, 102, 241, 0.4);
    }

    .brand-icon svg {
      width: 20px;
      height: 20px;
      fill: #ffffff;
    }

    .brand-name {
      font-size: 1.35rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      background: var(--accent-gradient);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.25rem 0.65rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
      border: 1px solid var(--border-color);
      background: rgba(255, 255, 255, 0.03);
    }

    .badge-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--accent-emerald);
      box-shadow: 0 0 8px var(--accent-emerald);
    }

    .nav-links {
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    .nav-link {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.875rem;
      transition: color 0.2s;
    }

    .nav-link:hover {
      color: var(--text-main);
    }

    /* Main Container */
    main {
      flex: 1;
      padding: 2rem;
      max-width: 1600px;
      margin: 0 auto;
      width: 100%;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.75rem;
    }

    @media (max-width: 1100px) {
      main {
        grid-template-columns: 1fr;
      }
    }

    /* Cards */
    .card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      backdrop-filter: blur(12px);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }

    .card-header {
      padding: 1.25rem 1.5rem;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: rgba(255, 255, 255, 0.015);
    }

    .card-title {
      font-size: 1.05rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .card-body {
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
      flex: 1;
    }

    /* Controls */
    .control-row {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
    }

    label {
      font-size: 0.8rem;
      font-weight: 500;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    select, input, textarea {
      background: var(--bg-input);
      color: var(--text-main);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      font-family: var(--font-mono);
      font-size: 0.85rem;
      padding: 0.65rem 0.85rem;
      outline: none;
      transition: all 0.2s ease;
      width: 100%;
    }

    select:focus, input:focus, textarea:focus {
      border-color: var(--accent-primary);
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
    }

    textarea {
      resize: vertical;
      line-height: 1.5;
    }

    .editor-container {
      position: relative;
      display: flex;
      flex-direction: column;
      flex: 1;
    }

    .editor-container textarea {
      min-height: 340px;
    }

    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      padding: 0.65rem 1.25rem;
      border-radius: 8px;
      font-family: var(--font-sans);
      font-size: 0.875rem;
      font-weight: 600;
      cursor: pointer;
      border: none;
      transition: all 0.2s ease;
    }

    .btn-primary {
      background: var(--accent-gradient);
      color: #ffffff;
      box-shadow: 0 4px 15px rgba(99, 102, 241, 0.35);
    }

    .btn-primary:hover {
      box-shadow: 0 6px 20px rgba(99, 102, 241, 0.55);
      transform: translateY(-1px);
    }

    .btn-secondary {
      background: rgba(255, 255, 255, 0.06);
      color: var(--text-main);
      border: 1px solid var(--border-color);
    }

    .btn-secondary:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.15);
    }

    .btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      transform: none !important;
    }

    /* DAG Nodes Display */
    .nodes-container {
      display: flex;
      flex-direction: column;
      gap: 0.85rem;
    }

    .node-card {
      background: rgba(14, 19, 32, 0.8);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 1rem 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .node-card:hover {
      border-color: var(--border-glow);
      background: var(--bg-card-hover);
      transform: translateX(3px);
    }

    .node-card.active {
      border-color: var(--accent-primary);
      box-shadow: 0 0 15px rgba(99, 102, 241, 0.2);
    }

    .node-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .node-id {
      font-family: var(--font-mono);
      font-size: 0.9rem;
      font-weight: 600;
      color: #ffffff;
    }

    .node-type-badge {
      font-size: 0.7rem;
      padding: 0.2rem 0.5rem;
      border-radius: 6px;
      font-weight: 600;
      letter-spacing: 0.03em;
    }

    .type-HTTP_DISPATCH { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }
    .type-PYTHON_WORKER { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }
    .type-LLM_AGENT { background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.3); }
    .type-DATA_TRANSFORM { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }

    .node-meta {
      display: flex;
      align-items: center;
      gap: 1rem;
      font-size: 0.78rem;
      color: var(--text-muted);
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.15rem 0.5rem;
      border-radius: 9999px;
    }

    .status-COMPLETED { color: var(--accent-emerald); background: rgba(16, 185, 129, 0.1); }
    .status-RUNNING { color: var(--accent-blue); background: rgba(56, 189, 248, 0.1); }
    .status-PENDING { color: var(--text-muted); background: rgba(255, 255, 255, 0.05); }
    .status-FAILED { color: var(--accent-rose); background: rgba(244, 63, 94, 0.1); }
    .status-CACHED { color: #a855f7; background: rgba(168, 85, 247, 0.15); border: 1px solid rgba(168, 85, 247, 0.3); }

    /* Inspection Panel */
    .inspector {
      background: var(--bg-input);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 1rem;
      max-height: 280px;
      overflow-y: auto;
      font-family: var(--font-mono);
      font-size: 0.8rem;
      line-height: 1.4;
      white-space: pre-wrap;
      word-break: break-all;
    }

    /* Metric pill */
    .metric-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      padding: 0.2rem 0.5rem;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.04);
      font-family: var(--font-mono);
      font-size: 0.75rem;
      color: var(--text-muted);
    }

    /* Spinner */
    .spinner {
      width: 14px;
      height: 14px;
      border: 2px solid rgba(255, 255, 255, 0.2);
      border-top-color: #ffffff;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    footer {
      border-top: 1px solid var(--border-color);
      padding: 1rem 2rem;
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-muted);
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-icon">
        <svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14l-5-5 1.41-1.41L12 14.17l7.59-7.59L21 8l-9 9z"/></svg>
      </div>
      <span class="brand-name">cloudag Studio</span>
      <span class="badge" id="server-status"><span class="badge-dot"></span> Online</span>
    </div>
    <div class="nav-links">
      <a href="/docs" target="_blank" class="nav-link">Swagger API Docs</a>
      <a href="https://github.com/somerandomguy-coder/cloudag" target="_blank" class="nav-link">GitHub</a>
    </div>
  </header>

  <main>
    <!-- Left Column: Workflow Definition & Execution -->
    <section class="card">
      <div class="card-header">
        <h2 class="card-title">Declarative DAG Workflow</h2>
        <div class="control-row">
          <select id="example-select" style="width: auto;">
            <option value="hybrid">Preset: Hybrid DAG (HTTP + Python + LLM)</option>
            <option value="data_pipeline">Preset: Data Transform Pipeline</option>
            <option value="webhook">Preset: Async Webhook Dispatch</option>
          </select>
        </div>
      </div>
      <div class="card-body">
        <div class="editor-container">
          <label for="workflow-json">Workflow JSON Definition</label>
          <textarea id="workflow-json" spellcheck="false"></textarea>
        </div>

        <div>
          <label for="input-json">Runtime Inputs (JSON)</label>
          <textarea id="input-json" rows="3" spellcheck="false">{\n  "topic": "AI Agents"\n}</textarea>
        </div>

        <div class="control-row" style="justify-content: space-between;">
          <button class="btn btn-secondary" id="btn-validate" onclick="validateGraph()">Validate DAG</button>
          <div style="display: flex; gap: 0.5rem;">
            <button class="btn btn-secondary" id="btn-warm" onclick="executeWorkflow(true)">Run with Cache</button>
            <button class="btn btn-primary" id="btn-run" onclick="executeWorkflow(false)">
              <span id="run-text">Execute Workflow</span>
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- Right Column: Visual DAG Execution & Inspector -->
    <section class="card">
      <div class="card-header">
        <h2 class="card-title">Live DAG Execution & Inspection</h2>
        <div id="run-meta" style="display: none;">
          <span class="metric-pill" id="total-time-pill">0 ms</span>
        </div>
      </div>
      <div class="card-body">
        <div id="empty-state" style="text-align: center; padding: 3rem 1rem; color: var(--text-muted);">
          <p>No active execution. Click <strong>Execute Workflow</strong> to observe dynamic fan-out execution, fan-in join barriers, and LLM steps.</p>
        </div>

        <div id="execution-view" style="display: none; flex-direction: column; gap: 1rem;">
          <div class="control-row" style="justify-content: space-between; border-bottom: 1px solid var(--border-color); padding-bottom: 0.75rem;">
            <div>
              <span style="font-size: 0.8rem; color: var(--text-muted);">RUN ID:</span>
              <span id="display-run-id" style="font-family: var(--font-mono); font-size: 0.85rem; font-weight: 600;"></span>
            </div>
            <span class="status-badge" id="workflow-status-badge">PENDING</span>
          </div>

          <!-- Nodes Step List -->
          <div class="nodes-container" id="nodes-list"></div>

          <!-- Selected Node Details -->
          <div>
            <label id="inspector-label">Step Outputs & Trace</label>
            <div class="inspector" id="node-inspector">Select a step above to inspect outputs.</div>
          </div>
        </div>
      </div>
    </section>
  </main>

  <footer>
    cloudag &mdash; Production Declarative JSON DAG Workflow Engine. Built with Python 3.11+, FastAPI, and SQLAlchemy 2.0.
  </footer>

  <script>
    const EXAMPLES = {
      hybrid: {
        workflow_id: "hybrid_insights_pipeline",
        version: "1.0.0",
        steps: [
          {
            id: "step_1",
            type: "HTTP_DISPATCH",
            action: "https://api.github.com",
            inputs: {
              "topic": "${workflow.input.topic}"
            },
            cache_executed_step: true
          },
          {
            id: "step_2",
            type: "PYTHON_WORKER",
            action: "len",
            inputs: {
              "code": "sorted(['Agentic Workflow', 'DAG Orchestration', 'Multi-Agent'])"
            },
            cache_executed_step: true
          },
          {
            id: "step_3",
            type: "LLM_AGENT",
            action: "gpt-4o",
            depends_on: ["step_1", "step_2"],
            inputs: {
              "prompt": "Synthesize insights for ${workflow.input.topic}. Upstream step 2 count: ${step_2.output}."
            },
            cache_executed_step: true
          }
        ]
      },
      data_pipeline: {
        workflow_id: "deterministic_data_pipeline",
        version: "1.0.0",
        steps: [
          {
            id: "extract_math",
            type: "PYTHON_WORKER",
            action: "math_expr",
            inputs: {
              "code": "[x ** 2 for x in range(5)]"
            }
          },
          {
            id: "transform_merge",
            type: "DATA_TRANSFORM",
            action: "merge",
            depends_on: ["extract_math"],
            inputs: {
              "squares": "${extract_math.output}",
              "metadata": { "processed": true }
            }
          }
        ]
      },
      webhook: {
        workflow_id: "async_callback_pipeline",
        version: "1.0.0",
        steps: [
          {
            id: "long_task",
            type: "PYTHON_WORKER",
            action: "none",
            inputs: {
              "wait_for_webhook": true
            },
            timeout_seconds: 60
          }
        ]
      }
    };

    const wfJsonEl = document.getElementById("workflow-json");
    const inputJsonEl = document.getElementById("input-json");
    const exampleSelect = document.getElementById("example-select");

    function loadPreset(key) {
      if (EXAMPLES[key]) {
        wfJsonEl.value = JSON.stringify(EXAMPLES[key], null, 2);
      }
    }

    exampleSelect.addEventListener("change", (e) => loadPreset(e.target.value));
    loadPreset("hybrid");

    let currentStepRuns = {};

    async function validateGraph() {
      try {
        const wf = JSON.parse(wfJsonEl.value);
        const res = await fetch("/api/v1/workflows", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(wf)
        });
        const data = await res.json();
        if (res.ok) {
          alert(`Workflow '${wf.workflow_id}' is a valid acyclic DAG!`);
        } else {
          alert(`Validation Error: ${data.detail || JSON.stringify(data)}`);
        }
      } catch (err) {
        alert("JSON Parse Error: " + err.message);
      }
    }

    async function executeWorkflow(useCache) {
      let wf, inputs;
      try {
        wf = JSON.parse(wfJsonEl.value);
        inputs = JSON.parse(inputJsonEl.value);
      } catch (e) {
        alert("Invalid JSON: " + e.message);
        return;
      }

      // Pre-register workflow
      await fetch("/api/v1/workflows", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(wf)
      });

      const btnRun = document.getElementById("btn-run");
      const runText = document.getElementById("run-text");
      btnRun.disabled = true;
      runText.innerHTML = '<span class="spinner"></span> Executing...';

      document.getElementById("empty-state").style.display = "none";
      document.getElementById("execution-view").style.display = "flex";
      document.getElementById("nodes-list").innerHTML = "";

      const t0 = performance.now();

      try {
        const res = await fetch(`/api/v1/workflows/${encodeURIComponent(wf.workflow_id)}/execute`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            inputs: inputs,
            wait_for_completion: true
          })
        });

        const elapsed = (performance.now() - t0).toFixed(1);
        const data = await res.json();

        btnRun.disabled = false;
        runText.innerText = "Execute Workflow";

        if (!res.ok) {
          alert("Execution Failed: " + (data.detail || JSON.stringify(data)));
          return;
        }

        document.getElementById("run-meta").style.display = "block";
        document.getElementById("total-time-pill").innerText = `${elapsed} ms`;
        document.getElementById("display-run-id").innerText = data.run_id;

        const badge = document.getElementById("workflow-status-badge");
        badge.innerText = data.status;
        badge.className = `status-badge status-${data.status}`;

        // Fetch detailed step runs
        const runRes = await fetch(`/api/v1/runs/${data.run_id}`);
        const runDetails = await runRes.json();

        renderNodes(wf.steps, runDetails.step_runs);
      } catch (err) {
        btnRun.disabled = false;
        runText.innerText = "Execute Workflow";
        alert("Error executing workflow: " + err.message);
      }
    }

    function renderNodes(steps, stepRuns) {
      const container = document.getElementById("nodes-list");
      container.innerHTML = "";
      currentStepRuns = {};

      const stepRunMap = {};
      (stepRuns || []).forEach(sr => { stepRunMap[sr.step_id] = sr; });

      steps.forEach((step, idx) => {
        const sr = stepRunMap[step.id];
        currentStepRuns[step.id] = sr;

        const card = document.createElement("div");
        card.className = "node-card" + (idx === 0 ? " active" : "");
        card.onclick = () => selectNode(step.id, card);

        const statusClass = sr ? (sr.cached ? "status-CACHED" : `status-${sr.status}`) : "status-PENDING";
        const statusText = sr ? (sr.cached ? "CACHED" : sr.status) : "PENDING";
        const durationText = sr && sr.duration_ms !== null ? `${sr.duration_ms.toFixed(1)} ms` : "-";

        card.innerHTML = `
          <div class="node-header">
            <span class="node-id">${step.id}</span>
            <span class="node-type-badge type-${step.type}">${step.type}</span>
          </div>
          <div class="node-meta">
            <span class="status-badge ${statusClass}">${statusText}</span>
            <span>Duration: <strong style="color:#ffffff;">${durationText}</strong></span>
            <span>Action: <code>${step.action}</code></span>
            ${step.depends_on && step.depends_on.length ? `<span>Depends on: [${step.depends_on.join(', ')}]</span>` : ''}
          </div>
        `;
        container.appendChild(card);
      });

      if (steps.length > 0) {
        selectNode(steps[0].id, container.children[0]);
      }
    }

    function selectNode(stepId, cardEl) {
      document.querySelectorAll(".node-card").forEach(el => el.classList.remove("active"));
      if (cardEl) cardEl.classList.add("active");

      document.getElementById("inspector-label").innerText = `Step Inspection &mdash; [${stepId}]`;
      const sr = currentStepRuns[stepId];
      if (sr) {
        document.getElementById("node-inspector").innerText = JSON.stringify({
          step_id: sr.step_id,
          status: sr.status,
          cached: sr.cached,
          duration_ms: sr.duration_ms,
          resolved_inputs: sr.resolved_inputs,
          outputs: sr.outputs,
          error_trace: sr.error_trace
        }, null, 2);
      } else {
        document.getElementById("node-inspector").innerText = "No execution record for this step.";
      }
    }
  </script>
</body>
</html>
"""
