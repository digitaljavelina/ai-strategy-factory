"""
Full-featured web application for AI Strategy Factory.

Features:
- Home page to enter company name and start analysis
- Real-time progress tracking during pipeline execution
- Results viewer with proper markdown rendering
- Download links for generated files

Usage:
    python -m strategy_factory.webapp

Then open http://localhost:5000 in your browser.
"""

import json
import os
import queue
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template_string, request, jsonify, Response, send_from_directory
from dotenv import load_dotenv

import markdown
from markdown.extensions.tables import TableExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.toc import TocExtension

from strategy_factory.config import OUTPUT_DIR, DELIVERABLES
from strategy_factory.models import CompanyInput, ResearchMode
from strategy_factory.progress_tracker import ProgressTracker, slugify

load_dotenv()

app = Flask(__name__)

# Store for active jobs and their progress
active_jobs = {}


# =============================================================================
# HTML Templates
# =============================================================================

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - AI Strategy Factory</title>
    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --primary-light: #dbeafe;
            --bg: #f8fafc;
            --card: #ffffff;
            --text: #1e293b;
            --text-secondary: #64748b;
            --border: #e2e8f0;
            --success: #22c55e;
            --success-light: #dcfce7;
            --warning: #f59e0b;
            --error: #ef4444;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            min-height: 100vh;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }

        header {
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            padding: 1.5rem 0;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }

        header .container {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        header h1 {
            font-size: 1.5rem;
            font-weight: 600;
        }

        header a {
            color: white;
            text-decoration: none;
            opacity: 0.9;
            transition: opacity 0.15s;
        }

        header a:hover {
            opacity: 1;
        }

        .card {
            background: var(--card);
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 1.5rem;
        }

        .card h2 {
            font-size: 1.25rem;
            margin-bottom: 1rem;
            color: var(--text);
        }

        .form-group {
            margin-bottom: 1.5rem;
        }

        .form-group label {
            display: block;
            font-weight: 500;
            margin-bottom: 0.5rem;
            color: var(--text);
        }

        .form-group small {
            display: block;
            color: var(--text-secondary);
            font-size: 0.875rem;
            margin-top: 0.25rem;
        }

        input[type="text"], textarea, select {
            width: 100%;
            padding: 0.75rem 1rem;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 1rem;
            transition: border-color 0.15s, box-shadow 0.15s;
        }

        input[type="text"]:focus, textarea:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px var(--primary-light);
        }

        textarea {
            min-height: 100px;
            resize: vertical;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.75rem 1.5rem;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.15s, transform 0.1s;
        }

        .btn:hover {
            background: var(--primary-dark);
        }

        .btn:active {
            transform: scale(0.98);
        }

        .btn:disabled {
            background: var(--text-secondary);
            cursor: not-allowed;
        }

        .btn-secondary {
            background: var(--bg);
            color: var(--text);
            border: 1px solid var(--border);
        }

        .btn-secondary:hover {
            background: var(--border);
        }

        .radio-group {
            display: flex;
            gap: 1rem;
        }

        .radio-option {
            flex: 1;
            padding: 1rem;
            border: 2px solid var(--border);
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.15s;
        }

        .radio-option:hover {
            border-color: var(--primary-light);
        }

        .radio-option.selected {
            border-color: var(--primary);
            background: var(--primary-light);
        }

        .radio-option input {
            display: none;
        }

        .radio-option h4 {
            font-size: 1rem;
            margin-bottom: 0.25rem;
        }

        .radio-option p {
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin: 0;
        }

        /* Progress page styles */
        .progress-container {
            max-width: 800px;
            margin: 3rem auto;
        }

        .progress-header {
            text-align: center;
            margin-bottom: 2rem;
        }

        .progress-header h2 {
            font-size: 1.75rem;
            margin-bottom: 0.5rem;
        }

        .progress-header p {
            color: var(--text-secondary);
        }

        .phase-list {
            list-style: none;
        }

        .phase-item {
            display: flex;
            align-items: flex-start;
            gap: 1rem;
            padding: 1.25rem;
            background: var(--card);
            border-radius: 8px;
            margin-bottom: 0.75rem;
            border: 1px solid var(--border);
            transition: all 0.3s;
        }

        .phase-item.active {
            border-color: var(--primary);
            box-shadow: 0 0 0 3px var(--primary-light);
        }

        .phase-item.completed {
            border-color: var(--success);
            background: var(--success-light);
        }

        .phase-icon {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1rem;
            flex-shrink: 0;
        }

        .phase-item.pending .phase-icon {
            background: var(--border);
            color: var(--text-secondary);
        }

        .phase-item.active .phase-icon {
            background: var(--primary);
            color: white;
            animation: pulse 1.5s infinite;
        }

        .phase-item.completed .phase-icon {
            background: var(--success);
            color: white;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }

        .phase-content {
            flex: 1;
        }

        .phase-content h4 {
            font-size: 1rem;
            margin-bottom: 0.25rem;
        }

        .phase-content p {
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin: 0;
        }

        .phase-progress {
            margin-top: 0.75rem;
        }

        .progress-bar {
            height: 6px;
            background: var(--border);
            border-radius: 3px;
            overflow: hidden;
        }

        .progress-fill {
            height: 100%;
            background: var(--primary);
            border-radius: 3px;
            transition: width 0.3s;
        }

        .progress-text {
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-top: 0.25rem;
        }

        .spinner {
            width: 20px;
            height: 20px;
            border: 2px solid var(--border);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Results page - sidebar layout */
        .results-layout {
            display: grid;
            grid-template-columns: 300px 1fr;
            gap: 2rem;
            min-height: calc(100vh - 200px);
        }

        .sidebar {
            background: var(--card);
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            height: fit-content;
            position: sticky;
            top: 1rem;
        }

        .sidebar h3 {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            margin-bottom: 0.75rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
        }

        .nav-list {
            list-style: none;
            margin-bottom: 1.5rem;
        }

        .nav-list li {
            margin-bottom: 0.25rem;
        }

        .nav-list a {
            display: block;
            padding: 0.5rem 0.75rem;
            color: var(--text);
            text-decoration: none;
            border-radius: 6px;
            font-size: 0.875rem;
            transition: all 0.15s;
        }

        .nav-list a:hover {
            background: var(--bg);
            color: var(--primary);
        }

        .nav-list a.active {
            background: var(--primary);
            color: white;
        }

        .download-btn {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 0.75rem;
            background: var(--bg);
            border-radius: 6px;
            text-decoration: none;
            color: var(--text);
            font-size: 0.875rem;
            margin-bottom: 0.5rem;
            transition: all 0.15s;
        }

        .download-btn:hover {
            background: var(--primary);
            color: white;
        }

        .download-btn .size {
            margin-left: auto;
            opacity: 0.6;
            font-size: 0.75rem;
        }

        .content {
            background: var(--card);
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        /* Markdown content styling */
        .markdown-content h1 { font-size: 1.75rem; margin-top: 0; margin-bottom: 1rem; }
        .markdown-content h2 { font-size: 1.5rem; margin-top: 2rem; margin-bottom: 0.75rem; border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; }
        .markdown-content h3 { font-size: 1.25rem; margin-top: 1.5rem; margin-bottom: 0.5rem; }
        .markdown-content h4 { font-size: 1.1rem; margin-top: 1.25rem; margin-bottom: 0.5rem; }

        .markdown-content p { margin-bottom: 1rem; }

        .markdown-content ul, .markdown-content ol {
            margin-bottom: 1rem;
            padding-left: 1.5rem;
        }

        .markdown-content li { margin-bottom: 0.5rem; }

        .markdown-content table {
            width: 100%;
            border-collapse: collapse;
            margin: 1.5rem 0;
            font-size: 0.9rem;
        }

        .markdown-content th, .markdown-content td {
            padding: 0.75rem 1rem;
            text-align: left;
            border: 1px solid var(--border);
        }

        .markdown-content th {
            background: var(--bg);
            font-weight: 600;
        }

        .markdown-content tr:nth-child(even) {
            background: var(--bg);
        }

        .markdown-content code {
            background: var(--bg);
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.875em;
        }

        .markdown-content pre {
            background: #1e293b;
            color: #e2e8f0;
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            margin: 1rem 0;
        }

        .markdown-content pre code {
            background: none;
            padding: 0;
            color: inherit;
        }

        .markdown-content blockquote {
            border-left: 4px solid var(--primary);
            padding-left: 1rem;
            margin: 1rem 0;
            color: var(--text-secondary);
        }

        .markdown-content hr {
            border: none;
            border-top: 1px solid var(--border);
            margin: 2rem 0;
        }

        /* Diagrams grid */
        .diagrams-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 1.5rem;
        }

        .diagram-card {
            background: var(--bg);
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
        }

        .diagram-card img {
            max-width: 100%;
            height: auto;
            border-radius: 4px;
            margin-bottom: 0.5rem;
            cursor: pointer;
            transition: transform 0.2s;
        }

        .diagram-card img:hover {
            transform: scale(1.02);
        }

        .diagram-card h4 {
            margin: 0;
            font-size: 0.875rem;
        }

        /* Stats header */
        .stats-bar {
            display: flex;
            gap: 2rem;
            padding: 1rem 1.5rem;
            background: var(--card);
            border-radius: 8px;
            margin-bottom: 1.5rem;
        }

        .stat-item {
            text-align: center;
        }

        .stat-value {
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--primary);
        }

        .stat-label {
            font-size: 0.75rem;
            color: var(--text-secondary);
            text-transform: uppercase;
        }

        /* Companies list */
        .companies-list {
            display: grid;
            gap: 1rem;
        }

        .company-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 1rem 1.5rem;
            background: var(--card);
            border-radius: 8px;
            border: 1px solid var(--border);
            text-decoration: none;
            color: var(--text);
            transition: all 0.15s;
        }

        .company-card:hover {
            border-color: var(--primary);
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .company-info h3 {
            font-size: 1.1rem;
            margin-bottom: 0.25rem;
        }

        .company-info p {
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin: 0;
        }

        .company-meta {
            text-align: right;
        }

        .company-meta .progress {
            font-weight: 600;
            color: var(--success);
        }

        .company-meta .cost {
            font-size: 0.875rem;
            color: var(--text-secondary);
        }

        @media (max-width: 900px) {
            .results-layout {
                grid-template-columns: 1fr;
            }

            .sidebar {
                position: relative;
                top: 0;
            }
        }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <a href="/"><h1>AI Strategy Factory</h1></a>
            <nav>
                <a href="/">New Analysis</a>
            </nav>
        </div>
    </header>

    <div class="container">
        {{ content|safe }}
    </div>

    {{ scripts|safe }}
</body>
</html>
"""

HOME_CONTENT = """
<div style="max-width: 700px; margin: 2rem auto;">
    <div class="card">
        <h2>Generate AI Strategy Deliverables</h2>
        <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">
            Enter a company name to generate comprehensive AI strategy documents including
            roadmaps, maturity assessments, ROI analysis, and implementation guides.
        </p>

        <form id="analysis-form" action="/start" method="POST">
            <div class="form-group">
                <label for="company">Company Name *</label>
                <input type="text" id="company" name="company" placeholder="e.g., Stripe, Airbnb, Shopify" required>
            </div>

            <div class="form-group">
                <label for="context">Additional Context</label>
                <textarea id="context" name="context" placeholder="Optional: Industry, company size, specific goals, current tech stack, etc."></textarea>
                <small>Help us tailor the analysis to your specific situation</small>
            </div>

            <div class="form-group">
                <label>Research Mode</label>
                <div class="radio-group">
                    <label class="radio-option selected" id="mode-quick">
                        <input type="radio" name="mode" value="quick" checked>
                        <h4>Quick</h4>
                        <p>~$0.05 | 2-3 minutes</p>
                    </label>
                    <label class="radio-option" id="mode-comprehensive">
                        <input type="radio" name="mode" value="comprehensive">
                        <h4>Comprehensive</h4>
                        <p>~$0.50 | 5-10 minutes</p>
                    </label>
                </div>
            </div>

            <button type="submit" class="btn" style="width: 100%;">
                Start Analysis
            </button>
        </form>
    </div>

    {% if companies %}
    <div class="card">
        <h2>Previous Analyses</h2>
        <div class="companies-list">
            {% for company in companies %}
            <a href="/results/{{ company.slug }}" class="company-card">
                <div class="company-info">
                    <h3>{{ company.name }}</h3>
                    <p>{{ company.phase }}</p>
                </div>
                <div class="company-meta">
                    <div class="progress">{{ company.progress }}%</div>
                    <div class="cost">${{ "%.4f"|format(company.cost) }}</div>
                </div>
            </a>
            {% endfor %}
        </div>
    </div>
    {% endif %}
</div>
"""

HOME_SCRIPTS = """
<script>
    document.querySelectorAll('.radio-option').forEach(option => {
        option.addEventListener('click', function() {
            document.querySelectorAll('.radio-option').forEach(o => o.classList.remove('selected'));
            this.classList.add('selected');
            this.querySelector('input').checked = true;
        });
    });
</script>
"""

PROGRESS_CONTENT = """
<div class="progress-container">
    <div class="progress-header">
        <h2>Analyzing {{ company_name }}</h2>
        <p id="status-text">Initializing...</p>
    </div>

    <div class="card">
        <ul class="phase-list" id="phase-list">
            <li class="phase-item active" id="phase-research">
                <div class="phase-icon"><div class="spinner"></div></div>
                <div class="phase-content">
                    <h4>Research Phase</h4>
                    <p id="research-status">Gathering company intelligence...</p>
                    <div class="phase-progress">
                        <div class="progress-bar"><div class="progress-fill" id="research-progress" style="width: 0%"></div></div>
                        <div class="progress-text" id="research-text">Starting...</div>
                    </div>
                </div>
            </li>
            <li class="phase-item pending" id="phase-synthesis">
                <div class="phase-icon">2</div>
                <div class="phase-content">
                    <h4>Synthesis Phase</h4>
                    <p id="synthesis-status">Waiting...</p>
                    <div class="phase-progress" style="display: none;">
                        <div class="progress-bar"><div class="progress-fill" id="synthesis-progress" style="width: 0%"></div></div>
                        <div class="progress-text" id="synthesis-text"></div>
                    </div>
                </div>
            </li>
            <li class="phase-item pending" id="phase-generation">
                <div class="phase-icon">3</div>
                <div class="phase-content">
                    <h4>Document Generation</h4>
                    <p id="generation-status">Waiting...</p>
                    <div class="phase-progress" style="display: none;">
                        <div class="progress-bar"><div class="progress-fill" id="generation-progress" style="width: 0%"></div></div>
                        <div class="progress-text" id="generation-text"></div>
                    </div>
                </div>
            </li>
        </ul>
    </div>

    <div id="error-container" style="display: none;">
        <div class="card" style="border-color: var(--error); background: #fef2f2;">
            <h3 style="color: var(--error);">Error</h3>
            <p id="error-message"></p>
            <a href="/" class="btn btn-secondary" style="margin-top: 1rem;">Try Again</a>
        </div>
    </div>
</div>
"""

PROGRESS_SCRIPTS = """
<script>
    const jobId = '{{ job_id }}';
    let eventSource;

    function updatePhase(phaseId, status, isActive, isCompleted) {
        const phase = document.getElementById('phase-' + phaseId);
        phase.classList.remove('pending', 'active', 'completed');

        if (isCompleted) {
            phase.classList.add('completed');
            phase.querySelector('.phase-icon').innerHTML = '&#10003;';
        } else if (isActive) {
            phase.classList.add('active');
            phase.querySelector('.phase-icon').innerHTML = '<div class="spinner"></div>';
            phase.querySelector('.phase-progress').style.display = 'block';
        } else {
            phase.classList.add('pending');
        }

        document.getElementById(phaseId + '-status').textContent = status;
    }

    function updateProgress(phaseId, progress, text) {
        document.getElementById(phaseId + '-progress').style.width = progress + '%';
        document.getElementById(phaseId + '-text').textContent = text;
    }

    function startEventStream() {
        eventSource = new EventSource('/progress/' + jobId);

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            console.log('Progress update:', data);

            document.getElementById('status-text').textContent = data.message || 'Processing...';

            if (data.phase === 'research') {
                updatePhase('research', data.status || 'Researching...', true, data.completed);
                if (data.progress !== undefined) {
                    updateProgress('research', data.progress, data.detail || '');
                }
            } else if (data.phase === 'synthesis') {
                updatePhase('research', 'Complete', false, true);
                updatePhase('synthesis', data.status || 'Synthesizing...', true, data.completed);
                if (data.progress !== undefined) {
                    updateProgress('synthesis', data.progress, data.detail || '');
                }
            } else if (data.phase === 'generation') {
                updatePhase('synthesis', 'Complete', false, true);
                updatePhase('generation', data.status || 'Generating...', true, data.completed);
                if (data.progress !== undefined) {
                    updateProgress('generation', data.progress, data.detail || '');
                }
            }

            if (data.complete) {
                eventSource.close();
                updatePhase('generation', 'Complete', false, true);
                document.getElementById('status-text').textContent = 'Analysis complete!';
                setTimeout(() => {
                    window.location.href = '/results/' + data.company_slug;
                }, 1000);
            }

            if (data.error) {
                eventSource.close();
                document.getElementById('error-container').style.display = 'block';
                document.getElementById('error-message').textContent = data.error;
                document.getElementById('status-text').textContent = 'Error occurred';
            }
        };

        eventSource.onerror = function(err) {
            console.error('EventSource error:', err);
        };
    }

    startEventStream();
</script>
"""


# =============================================================================
# Routes
# =============================================================================

@app.route('/')
def home():
    """Home page with form to start new analysis."""
    # Get list of previous analyses
    companies = []
    if OUTPUT_DIR.exists():
        for item in OUTPUT_DIR.iterdir():
            if item.is_dir() and (item / "state.json").exists():
                try:
                    tracker = ProgressTracker(item.name)
                    summary = tracker.get_progress_summary()
                    companies.append({
                        "name": summary["company_name"],
                        "slug": item.name,
                        "phase": summary["current_phase"],
                        "progress": summary["deliverables"]["progress_percent"],
                        "cost": summary["costs"]["total"],
                    })
                except:
                    pass

    from jinja2 import Template
    content = Template(HOME_CONTENT).render(companies=sorted(companies, key=lambda x: x["name"]))

    return render_template_string(
        BASE_TEMPLATE,
        title="Home",
        content=content,
        scripts=HOME_SCRIPTS
    )


@app.route('/start', methods=['POST'])
def start_analysis():
    """Start a new analysis job."""
    company_name = request.form.get('company', '').strip()
    context = request.form.get('context', '').strip()
    mode = request.form.get('mode', 'quick')

    if not company_name:
        return jsonify({"error": "Company name is required"}), 400

    # Generate a job ID
    job_id = str(uuid.uuid4())[:8]
    company_slug = slugify(company_name)

    # Create job entry
    active_jobs[job_id] = {
        "company_name": company_name,
        "company_slug": company_slug,
        "context": context,
        "mode": mode,
        "status": "starting",
        "progress_queue": queue.Queue(),
        "started_at": datetime.now(),
    }

    # Start the pipeline in a background thread
    thread = threading.Thread(
        target=run_pipeline,
        args=(job_id, company_name, context, mode),
        daemon=True
    )
    thread.start()

    # Redirect to progress page
    from jinja2 import Template
    content = Template(PROGRESS_CONTENT).render(company_name=company_name)
    scripts = Template(PROGRESS_SCRIPTS).render(job_id=job_id)

    return render_template_string(
        BASE_TEMPLATE,
        title=f"Analyzing {company_name}",
        content=content,
        scripts=scripts
    )


@app.route('/progress/<job_id>')
def progress_stream(job_id):
    """Server-Sent Events stream for progress updates."""
    if job_id not in active_jobs:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        job = active_jobs[job_id]
        q = job["progress_queue"]

        while True:
            try:
                # Wait for progress update
                update = q.get(timeout=30)
                yield f"data: {json.dumps(update)}\n\n"

                if update.get("complete") or update.get("error"):
                    break
            except queue.Empty:
                # Send keepalive
                yield f"data: {json.dumps({'keepalive': True})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/results/<company_slug>')
def results(company_slug):
    """View results for a company."""
    output_dir = OUTPUT_DIR / company_slug

    if not output_dir.exists():
        return "Company not found", 404

    tracker = ProgressTracker(company_slug)
    summary = tracker.get_progress_summary()

    # Get markdown files
    markdown_files = []
    markdown_dir = output_dir / "markdown"
    if markdown_dir.exists():
        for md_file in sorted(markdown_dir.glob("*.md")):
            markdown_files.append({
                "name": md_file.stem.replace("_", " ").title(),
                "filename": md_file.name,
            })

    # Get diagrams
    mermaid_images = []
    mermaid_dir = output_dir / "mermaid_images"
    if mermaid_dir.exists():
        for img in sorted(mermaid_dir.glob("*.png")):
            mermaid_images.append({
                "name": img.stem.replace("_", " ").title(),
                "filename": img.name,
            })

    # Get presentations and documents
    presentations = []
    pres_dir = output_dir / "presentations"
    if pres_dir.exists():
        for pptx in sorted(pres_dir.glob("*.pptx")):
            presentations.append({
                "name": pptx.stem.replace("_", " ").title(),
                "filename": pptx.name,
                "size": f"{pptx.stat().st_size / 1024:.1f} KB"
            })

    documents = []
    docs_dir = output_dir / "documents"
    if docs_dir.exists():
        for docx in sorted(docs_dir.glob("*.docx")):
            documents.append({
                "name": docx.stem.replace("_", " ").title(),
                "filename": docx.name,
                "size": f"{docx.stat().st_size / 1024:.1f} KB"
            })

    content = render_results_page(
        company_name=summary["company_name"],
        company_slug=company_slug,
        total_cost=summary["costs"]["total"],
        markdown_files=markdown_files,
        mermaid_images=mermaid_images,
        presentations=presentations,
        documents=documents
    )

    return render_template_string(
        BASE_TEMPLATE,
        title=summary["company_name"],
        content=content,
        scripts=RESULTS_SCRIPTS
    )


def fix_malformed_tables(content: str) -> str:
    """Fix malformed markdown tables with overly long separator rows."""
    import re
    lines = content.split('\n')
    fixed_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Skip extremely long lines (likely malformed)
        if len(line) > 500:
            i += 1
            continue

        # Check if this looks like a table header row (has multiple | but not a separator)
        if line.count('|') >= 2 and not re.match(r'^\s*\|[\s\-:]+\|', line):
            cols = [c.strip() for c in line.split('|')]
            cols = [c for c in cols if c]
            num_cols = len(cols)

            if num_cols >= 2:
                # Check if next line is a malformed separator (too long)
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if len(next_line) > 200 and '-' in next_line:
                        # Create proper separator
                        separator = '|' + '|'.join([' --- ' for _ in range(num_cols)]) + '|'
                        fixed_lines.append(line)
                        fixed_lines.append(separator)
                        # Add a note that table data was unavailable
                        fixed_lines.append('')
                        fixed_lines.append('*Table data not available in source document.*')
                        fixed_lines.append('')
                        i += 2
                        continue

        fixed_lines.append(line)
        i += 1

    return '\n'.join(fixed_lines)


@app.route('/api/markdown/<company_slug>/<filename>')
def get_markdown(company_slug, filename):
    """Get rendered markdown content."""
    md_path = OUTPUT_DIR / company_slug / "markdown" / filename

    if not md_path.exists():
        return "File not found", 404

    with open(md_path, "r") as f:
        content = f.read()

    # Remove YAML frontmatter if present
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].strip()

    # Fix malformed tables
    content = fix_malformed_tables(content)

    # Convert markdown to HTML
    html = markdown.markdown(
        content,
        extensions=[
            TableExtension(),
            FencedCodeExtension(),
            TocExtension(),
            'nl2br'
        ]
    )

    return f'<div class="markdown-content">{html}</div>'


@app.route('/files/<company_slug>/<path:filepath>')
def serve_file(company_slug, filepath):
    """Serve static files (images, presentations, documents)."""
    directory = OUTPUT_DIR / company_slug
    return send_from_directory(directory, filepath)


def render_results_page(company_name, company_slug, total_cost, markdown_files, mermaid_images, presentations, documents):
    """Render the results page HTML."""
    html = f"""
    <div class="stats-bar">
        <div class="stat-item">
            <div class="stat-value">{len(markdown_files)}</div>
            <div class="stat-label">Deliverables</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">{len(mermaid_images)}</div>
            <div class="stat-label">Diagrams</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">${total_cost:.4f}</div>
            <div class="stat-label">Total Cost</div>
        </div>
    </div>

    <div class="results-layout">
        <aside class="sidebar">
            <h3>Strategy Documents</h3>
            <ul class="nav-list" id="doc-list">
    """

    for md in markdown_files:
        html += f'<li><a href="#" data-file="{md["filename"]}" class="doc-link">{md["name"]}</a></li>\n'

    html += """
            </ul>

            <h3>Diagrams</h3>
            <ul class="nav-list">
                <li><a href="#" id="show-diagrams">View All Diagrams</a></li>
            </ul>
    """

    if presentations:
        html += '<h3>Presentations</h3>\n'
        for pres in presentations:
            html += f'<a href="/files/{company_slug}/presentations/{pres["filename"]}" class="download-btn" download>📊 {pres["name"]}<span class="size">{pres["size"]}</span></a>\n'

    if documents:
        html += '<h3>Documents</h3>\n'
        for doc in documents:
            html += f'<a href="/files/{company_slug}/documents/{doc["filename"]}" class="download-btn" download>📄 {doc["name"]}<span class="size">{doc["size"]}</span></a>\n'

    html += f"""
        </aside>

        <main class="content" id="content">
            <div style="text-align: center; padding: 3rem;">
                <h2>Welcome to {company_name}'s AI Strategy</h2>
                <p style="color: var(--text-secondary); max-width: 500px; margin: 1rem auto 2rem;">
                    Select a document from the sidebar to view the analysis, or download the presentations and reports.
                </p>
            </div>
        </main>
    </div>

    <script>
        const companySlug = '{company_slug}';
        const diagramsHtml = `
            <h2>System Architecture Diagrams</h2>
            <div class="diagrams-grid">
    """

    for img in mermaid_images:
        html += f'<div class="diagram-card"><img src="/files/{company_slug}/mermaid_images/{img["filename"]}" alt="{img["name"]}"><h4>{img["name"]}</h4></div>\n'

    html += """
            </div>
        `;
    </script>
    """

    return html


RESULTS_SCRIPTS = """
<script>
    document.addEventListener('DOMContentLoaded', function() {
        // Document links
        document.querySelectorAll('.doc-link').forEach(link => {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                const filename = this.getAttribute('data-file');

                // Update active state
                document.querySelectorAll('.doc-link').forEach(l => l.classList.remove('active'));
                this.classList.add('active');

                // Load content
                fetch('/api/markdown/' + companySlug + '/' + filename)
                    .then(response => response.text())
                    .then(html => {
                        document.getElementById('content').innerHTML = html;
                    })
                    .catch(err => {
                        document.getElementById('content').innerHTML = '<p>Error loading content.</p>';
                    });
            });
        });

        // Diagrams link
        document.getElementById('show-diagrams').addEventListener('click', function(e) {
            e.preventDefault();
            document.querySelectorAll('.doc-link').forEach(l => l.classList.remove('active'));
            document.getElementById('content').innerHTML = diagramsHtml;
        });

        // Load first document by default
        const firstDoc = document.querySelector('.doc-link');
        if (firstDoc) firstDoc.click();
    });
</script>
"""


# =============================================================================
# Pipeline Execution
# =============================================================================

def run_pipeline(job_id: str, company_name: str, context: str, mode: str):
    """Run the full pipeline in a background thread."""
    job = active_jobs[job_id]
    q = job["progress_queue"]

    try:
        # Import here to avoid circular imports
        from strategy_factory.models import CompanyInput, ResearchMode
        from strategy_factory.progress_tracker import ProgressTracker
        from strategy_factory.research.orchestrator import ResearchOrchestrator
        from strategy_factory.synthesis.orchestrator import SynthesisOrchestrator
        from strategy_factory.generation.orchestrator import GenerationOrchestrator

        research_mode = ResearchMode.QUICK if mode == "quick" else ResearchMode.COMPREHENSIVE

        company_input = CompanyInput(
            name=company_name,
            context=context,
            mode=research_mode,
        )

        tracker = ProgressTracker(company_name, company_input)

        # Phase 1: Research
        q.put({
            "phase": "research",
            "message": "Starting research...",
            "status": "Gathering company intelligence",
            "progress": 0,
            "detail": "Initializing"
        })

        def research_callback(message: str, progress: float):
            q.put({
                "phase": "research",
                "message": f"Research: {message}",
                "status": "Researching",
                "progress": int(progress * 100),
                "detail": message
            })

        research_orchestrator = ResearchOrchestrator(
            mode=research_mode,
            cache_dir=Path(tracker.output_dir),
            progress_callback=research_callback,
        )

        research_output = research_orchestrator.research(company_input)
        tracker.save_research_output(research_output)
        research_orchestrator.save_research_cache(Path(tracker.output_dir))

        q.put({
            "phase": "research",
            "completed": True,
            "message": "Research complete"
        })

        # Phase 2: Synthesis
        q.put({
            "phase": "synthesis",
            "message": "Starting synthesis...",
            "status": "Generating deliverables",
            "progress": 0,
            "detail": "Initializing"
        })

        def synthesis_callback(message: str, progress: float):
            q.put({
                "phase": "synthesis",
                "message": f"Synthesis: {message}",
                "status": "Synthesizing",
                "progress": int(progress * 100),
                "detail": message
            })

        synthesis_orchestrator = SynthesisOrchestrator(
            output_dir=OUTPUT_DIR,
            progress_callback=synthesis_callback,
        )

        synthesis_output = synthesis_orchestrator.synthesize(company_input, research_output)
        file_paths = synthesis_orchestrator.save_deliverables(tracker.company_slug)

        for d_id, path in file_paths.items():
            tracker.complete_deliverable(d_id, path)

        q.put({
            "phase": "synthesis",
            "completed": True,
            "message": "Synthesis complete"
        })

        # Phase 3: Generation
        q.put({
            "phase": "generation",
            "message": "Starting document generation...",
            "status": "Creating presentations and reports",
            "progress": 0,
            "detail": "Initializing"
        })

        def generation_callback(message: str, progress: float):
            q.put({
                "phase": "generation",
                "message": f"Generation: {message}",
                "status": "Generating",
                "progress": int(progress * 100),
                "detail": message
            })

        generation_orchestrator = GenerationOrchestrator(
            output_dir=OUTPUT_DIR,
            progress_callback=generation_callback,
        )

        result = generation_orchestrator.generate_all(
            company_slug=tracker.company_slug,
            company_input=company_input,
            research=research_output,
            synthesis=synthesis_output,
        )

        q.put({
            "phase": "generation",
            "completed": True,
            "message": "Generation complete"
        })

        # Complete
        q.put({
            "complete": True,
            "company_slug": tracker.company_slug,
            "message": "Analysis complete!"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        q.put({
            "error": str(e),
            "message": "Error occurred"
        })


# =============================================================================
# Main
# =============================================================================

def main():
    """Run the web application."""
    import argparse
    import socket

    parser = argparse.ArgumentParser(description="AI Strategy Factory Web App")
    parser.add_argument("--port", "-p", type=int, default=8888, help="Port to run on (default: 8888)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    args = parser.parse_args()

    # Check for API key
    if not os.getenv("OPENROUTER_API_KEY"):
        print("Warning: Missing API key: OPENROUTER_API_KEY")
        print("Set this in your .env file for full functionality.")
        print("Get a key at https://openrouter.ai/keys\n")

    import webbrowser

    # Find an available port if default is in use
    port = args.port
    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    if is_port_in_use(port):
        print(f"Port {port} is in use, trying alternatives...")
        for alt_port in [8889, 8890, 9000, 9001]:
            if not is_port_in_use(alt_port):
                port = alt_port
                break
        else:
            print("Error: Could not find an available port. Try specifying one with --port")
            return 1

    url = f"http://localhost:{port}"

    print("\n" + "=" * 50)
    print("AI Strategy Factory Web App")
    print("=" * 50)
    print(f"Server running at: {url}")
    print("Press Ctrl+C to stop\n")

    if not args.no_browser:
        webbrowser.open(url)

    try:
        app.run(host=args.host, port=port, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nServer stopped.")
        return 0


if __name__ == "__main__":
    main()
