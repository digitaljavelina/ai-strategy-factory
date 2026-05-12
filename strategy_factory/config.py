"""
Configuration constants and settings for the AI Strategy Factory.
"""

from pathlib import Path
from enum import Enum
from typing import Dict, List

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
TLDR_GUIDES_DIR = PROJECT_ROOT / "Consulting Guides TLDR"
PROGRESS_DIR = PROJECT_ROOT / "progress"

# API Configuration
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_REQUEST_DELAY = 5  # seconds between requests

# Perplexity models and their use cases
class PerplexityModel(str, Enum):
    SONAR = "sonar"
    SONAR_PRO = "sonar-pro"
    SONAR_REASONING = "sonar-reasoning"
    SONAR_REASONING_PRO = "sonar-reasoning-pro"
    SONAR_DEEP_RESEARCH = "sonar-deep-research"

# Research mode configuration
class ResearchMode(str, Enum):
    QUICK = "quick"
    COMPREHENSIVE = "comprehensive"

RESEARCH_MODE_MODELS: Dict[ResearchMode, List[PerplexityModel]] = {
    ResearchMode.QUICK: [PerplexityModel.SONAR],
    ResearchMode.COMPREHENSIVE: [
        PerplexityModel.SONAR,
        PerplexityModel.SONAR_PRO,
        PerplexityModel.SONAR_REASONING,
    ],
}

# Estimated costs per 1K tokens (input/output)
PERPLEXITY_COSTS = {
    PerplexityModel.SONAR: (0.001, 0.001),
    PerplexityModel.SONAR_PRO: (0.003, 0.015),
    PerplexityModel.SONAR_REASONING: (0.001, 0.005),
    PerplexityModel.SONAR_REASONING_PRO: (0.002, 0.008),
    PerplexityModel.SONAR_DEEP_RESEARCH: (0.002, 0.008),
}

# Deliverable definitions
DELIVERABLES = {
    # Markdown deliverables
    "01_tech_inventory": {
        "name": "Technology Inventory & Data Infrastructure Assessment",
        "format": "markdown",
        "dependencies": [],
        "tldr_guides": ["ceos-guide-to-generative-ai-second-edition_TLDR.md"]
    },
    "02_pain_points": {
        "name": "Pain Point Matrix by Department",
        "format": "markdown",
        "dependencies": [],
        "tldr_guides": ["us-state-of-gen-ai-2024-q4_TLDR.md"]
    },
    "03_mermaid_diagrams": {
        "name": "Mermaid Diagrams (Current State + Future State)",
        "format": "markdown",
        "dependencies": ["01_tech_inventory", "02_pain_points"],
        "tldr_guides": []
    },
    "04_maturity_assessment": {
        "name": "AI Maturity Model & Readiness Assessment",
        "format": "markdown",
        "dependencies": ["01_tech_inventory", "02_pain_points"],
        "tldr_guides": [
            "bcg-wheres-the-value-in-ai_TLDR.md",
            "CRI-research-brief-Harnessing-the-value-of-AI-AD_100925_TLDR.md"
        ]
    },
    "05_roadmap": {
        "name": "30/60/90/180/360 Implementation Roadmap",
        "format": "markdown",
        "dependencies": ["04_maturity_assessment", "14_use_case_library"],
        "tldr_guides": [
            "seizing-the-agentic-ai-advantage_TLDR.md",
            "the-agentic-organization-contours-of-the-next-paradigm-for-the-ai-era_TLDR.md"
        ]
    },
    "06_quick_wins": {
        "name": "Quick Wins List",
        "format": "markdown",
        "dependencies": ["14_use_case_library", "04_maturity_assessment"],
        "tldr_guides": [
            "identifying-and-scaling-ai-use-cases_TLDR.md",
            "bcg-wheres-the-value-in-ai_TLDR.md"
        ]
    },
    "07_vendor_comparison": {
        "name": "Vendor Comparison & Build vs Buy Framework",
        "format": "markdown",
        "dependencies": ["01_tech_inventory", "14_use_case_library"],
        "tldr_guides": ["ceos-guide-to-generative-ai-second-edition_TLDR.md"]
    },
    "08_license_consolidation": {
        "name": "License Consolidation Recommendations",
        "format": "markdown",
        "dependencies": ["01_tech_inventory", "07_vendor_comparison"],
        "tldr_guides": ["ceos-guide-to-generative-ai-second-edition_TLDR.md"]
    },
    "09_roi_calculator": {
        "name": "ROI Calculator & Cost Analysis",
        "format": "markdown",
        "dependencies": ["06_quick_wins", "14_use_case_library"],
        "tldr_guides": [
            "google_cloud_roi_of_ai_2025_TLDR.md",
            "bcg-wheres-the-value-in-ai_TLDR.md"
        ]
    },
    "10_ai_policy": {
        "name": "AI Acceptable Use Policy Template",
        "format": "markdown",
        "dependencies": ["04_maturity_assessment"],
        "tldr_guides": [
            "ceos-guide-to-generative-ai-second-edition_TLDR.md",
            "kpmg-agentic-ai-advantage_TLDR.md"
        ]
    },
    "11_data_governance": {
        "name": "Data Governance Framework",
        "format": "markdown",
        "dependencies": ["01_tech_inventory", "10_ai_policy"],
        "tldr_guides": ["ceos-guide-to-generative-ai-second-edition_TLDR.md"]
    },
    "12_prompt_library": {
        "name": "Prompt Library Starter Kit",
        "format": "markdown",
        "dependencies": ["14_use_case_library"],
        "tldr_guides": []
    },
    "13_glossary": {
        "name": "Glossary of AI Terms",
        "format": "markdown",
        "dependencies": [],
        "tldr_guides": []
    },
    "14_use_case_library": {
        "name": "Department-Specific Use Case Library",
        "format": "markdown",
        "dependencies": ["01_tech_inventory", "02_pain_points"],
        "tldr_guides": [
            "identifying-and-scaling-ai-use-cases_TLDR.md",
            "kpmg-agentic-ai-advantage_TLDR.md",
            "seizing-the-agentic-ai-advantage_TLDR.md"
        ]
    },
    "15_change_management": {
        "name": "Change Management & Training Playbook",
        "format": "markdown",
        "dependencies": ["05_roadmap", "14_use_case_library"],
        "tldr_guides": [
            "the-agentic-organization-contours-of-the-next-paradigm-for-the-ai-era_TLDR.md",
            "seizing-the-agentic-ai-advantage_TLDR.md"
        ]
    },
    # PowerPoint deliverables
    "executive_summary_deck": {
        "name": "Executive Summary Deck",
        "format": "pptx",
        "dependencies": ["ALL_MARKDOWN"],
        "tldr_guides": []
    },
    "full_findings_presentation": {
        "name": "Full Findings & Recommendations Presentation",
        "format": "pptx",
        "dependencies": ["ALL_MARKDOWN"],
        "tldr_guides": []
    },
    # Word document deliverables
    "final_strategy_report": {
        "name": "Final AI Strategy Report",
        "format": "docx",
        "dependencies": ["ALL_MARKDOWN"],
        "tldr_guides": []
    },
    "statement_of_work": {
        "name": "Statement of Work / Engagement Letter",
        "format": "docx",
        "dependencies": ["05_roadmap", "06_quick_wins", "09_roi_calculator"],
        "tldr_guides": []
    }
}

# Company size tiers for SOW pricing
class CompanySize(str, Enum):
    SMALL = "small"       # <100 employees
    MEDIUM = "medium"     # 100-500 employees
    LARGE = "large"       # 500-2000 employees
    ENTERPRISE = "enterprise"  # 2000+ employees

SOW_PRICING_MULTIPLIERS = {
    CompanySize.SMALL: 1.0,
    CompanySize.MEDIUM: 1.5,
    CompanySize.LARGE: 2.0,
    CompanySize.ENTERPRISE: None  # Custom pricing
}

# Base SOW pricing (in USD)
SOW_BASE_PRICING = {
    "discovery": 5000,
    "strategy": 10000,
    "implementation_support": 15000,
    "training": 5000,
    "total_base": 35000
}

# TLDR guide to topic mapping for selective loading
TLDR_TOPIC_MAPPING = {
    "maturity": [
        "bcg-wheres-the-value-in-ai_TLDR.md",
        "CRI-research-brief-Harnessing-the-value-of-AI-AD_100925_TLDR.md"
    ],
    "use_cases": [
        "identifying-and-scaling-ai-use-cases_TLDR.md",
        "kpmg-agentic-ai-advantage_TLDR.md",
        "seizing-the-agentic-ai-advantage_TLDR.md"
    ],
    "roi": [
        "google_cloud_roi_of_ai_2025_TLDR.md",
        "bcg-wheres-the-value-in-ai_TLDR.md"
    ],
    "governance": [
        "ceos-guide-to-generative-ai-second-edition_TLDR.md",
        "kpmg-agentic-ai-advantage_TLDR.md"
    ],
    "agentic": [
        "kpmg-agentic-ai-advantage_TLDR.md",
        "seizing-the-agentic-ai-advantage_TLDR.md",
        "the-agentic-organization-contours-of-the-next-paradigm-for-the-ai-era_TLDR.md"
    ],
    "platforms": [
        "ceos-guide-to-generative-ai-second-edition_TLDR.md"
    ],
    "market_trends": [
        "us-state-of-gen-ai-2024-q4_TLDR.md"
    ]
}

# Quality domain list for research validation
QUALITY_DOMAINS = [
    "bloomberg.com", "reuters.com", "forbes.com", "wsj.com",
    "techcrunch.com", "crunchbase.com", "linkedin.com", "sec.gov",
    "mckinsey.com", "bcg.com", "deloitte.com", "gartner.com",
    "hbr.org", "mit.edu", "stanford.edu", "accenture.com"
]

# Retry configuration
RETRY_CONFIG = {
    "max_retries": 3,
    "initial_delay": 5,
    "max_delay": 60,
    "backoff_multiplier": 2
}
