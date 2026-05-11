# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Strategy Factory generates comprehensive AI strategy deliverables for any company using Perplexity Sonar models for research and Google Gemini for document synthesis. Both providers are accessed through a single OpenRouter API key (no direct Perplexity or Google API access required).

**What it produces:**
- 15 strategic markdown documents
- 2 PowerPoint presentations
- 2 Word documents
- Architecture diagrams (Mermaid → PNG)

## Quick Commands

### Setup (First Time)
```bash
# Option 1: Automated setup
python setup.py

# Option 2: Manual setup
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# OR: .\venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### Run the Web App
```bash
source venv/bin/activate  # macOS/Linux
python -m strategy_factory.webapp
# Opens http://localhost:8888 automatically
```

### Run via CLI
```bash
# Full pipeline for a company
python -m strategy_factory.main run "Company Name"

# With additional context
python -m strategy_factory.main run "Stripe" --context "B2B payments, fintech"

# Comprehensive research (more thorough, costs more)
python -m strategy_factory.main run "Company Name" --mode comprehensive

# Dry run (no API calls)
python -m strategy_factory.main run "Company Name" --dry-run

# Check status of existing analysis
python -m strategy_factory.main status "Company Name"

# Resume interrupted pipeline
python -m strategy_factory.main resume "Company Name"
```

## Architecture

```
strategy_factory/
├── main.py              # CLI entry point
├── webapp.py            # Flask web application
├── config.py            # Configuration & deliverable definitions
├── models.py            # Pydantic data models
├── progress_tracker.py  # State management
├── research/            # Phase 1: Perplexity research
│   ├── orchestrator.py
│   ├── perplexity_client.py
│   └── queries.py
├── synthesis/           # Phase 2: Gemini document generation
│   ├── orchestrator.py
│   ├── gemini_client.py
│   ├── context_builder.py
│   └── prompts/         # 15 deliverable prompts
└── generation/          # Phase 3: Final outputs
    ├── orchestrator.py
    ├── pptx_generator.py
    ├── docx_generator.py
    └── mermaid_renderer.py
```

## Pipeline Flow

1. **Research Phase** → Perplexity API
   - Company overview, tech stack, competitors
   - Industry landscape, pain points
   - 9-18 queries depending on mode

2. **Synthesis Phase** → Gemini API
   - 15 markdown deliverables
   - Mermaid diagram code

3. **Generation Phase** → Local
   - PPTX presentations
   - DOCX reports
   - PNG diagram rendering

## Environment Variables

Required in `.env`:
```
OPENROUTER_API_KEY=sk-or-v1-xxx
```

Get a key at https://openrouter.ai/keys. One key gives the project access to
both Perplexity Sonar (research) and Google Gemini (synthesis), routed via
OpenRouter's OpenAI-compatible chat completions API.

## Output Structure

```
output/{company-slug}/
├── markdown/              # 15 .md files
├── presentations/         # 2 .pptx files
├── documents/             # 2 .docx files
├── mermaid_images/        # Architecture PNGs
├── research_cache.json    # Raw research data
└── state.json             # Progress tracking
```

## Key Files for Development

- `config.py` - Add new deliverables here
- `synthesis/prompts/*.py` - Edit document prompts
- `research/queries.py` - Modify research queries
- `webapp.py` - Web UI customization

## Troubleshooting

**Port in use:** App auto-finds available port, or use `--port 9000`

**Missing API key:** Check `.env` file exists and `OPENROUTER_API_KEY` is set

**Tables not rendering:** Known issue with some Gemini outputs - being handled in `fix_malformed_tables()`

## Cost Estimates

- Quick mode: ~$0.05 per company
- Comprehensive mode: ~$0.50 per company
