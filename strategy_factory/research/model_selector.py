"""
Model selection logic for Perplexity research.

Handles the selection of appropriate Perplexity models based on:
- Research mode (Quick vs Comprehensive)
- Query type and complexity
- Company information availability (public vs private)
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..config import PerplexityModel, ResearchMode, RESEARCH_MODE_MODELS, PERPLEXITY_COSTS
from ..models import CompanyInfoTier
from .query_templates import QueryCategory


@dataclass
class ModelSelection:
    """Represents a model selection with reasoning."""
    model: PerplexityModel
    reason: str
    estimated_cost: float
    fallback_model: Optional[PerplexityModel] = None


class ModelSelector:
    """
    Selects appropriate Perplexity models for research queries.
    
    Selection is based on:
    - Research mode (quick = sonar only, comprehensive = multiple models)
    - Query category (news vs deep research)
    - Company information tier (public companies need less deep research)
    """
    
    # Model recommendations by query category
    CATEGORY_MODELS: Dict[QueryCategory, Dict[ResearchMode, PerplexityModel]] = {
        QueryCategory.COMPANY_PROFILE: {
            ResearchMode.QUICK: PerplexityModel.SONAR,
            ResearchMode.COMPREHENSIVE: PerplexityModel.SONAR_PRO,
        },
        QueryCategory.INDUSTRY: {
            ResearchMode.QUICK: PerplexityModel.SONAR,
            ResearchMode.COMPREHENSIVE: PerplexityModel.SONAR_PRO,
        },
        QueryCategory.COMPETITORS: {
            ResearchMode.QUICK: PerplexityModel.SONAR,
            ResearchMode.COMPREHENSIVE: PerplexityModel.SONAR_PRO,
        },
        QueryCategory.TECHNOLOGY: {
            ResearchMode.QUICK: PerplexityModel.SONAR,
            ResearchMode.COMPREHENSIVE: PerplexityModel.SONAR_PRO,
        },
        QueryCategory.AI_INITIATIVES: {
            ResearchMode.QUICK: PerplexityModel.SONAR,
            ResearchMode.COMPREHENSIVE: PerplexityModel.SONAR_PRO,
        },
        QueryCategory.REGULATORY: {
            ResearchMode.QUICK: PerplexityModel.SONAR,
            ResearchMode.COMPREHENSIVE: PerplexityModel.SONAR_REASONING,
        },
        QueryCategory.NEWS: {
            ResearchMode.QUICK: PerplexityModel.SONAR,
            ResearchMode.COMPREHENSIVE: PerplexityModel.SONAR,
        },
        QueryCategory.LEADERSHIP: {
            ResearchMode.QUICK: PerplexityModel.SONAR,
            ResearchMode.COMPREHENSIVE: PerplexityModel.SONAR_PRO,
        },
        QueryCategory.FUNDING: {
            ResearchMode.QUICK: PerplexityModel.SONAR,
            ResearchMode.COMPREHENSIVE: PerplexityModel.SONAR_PRO,
        },
    }
    
    # Information tier adjustments
    # For public companies with lots of info, we can use simpler models
    TIER_UPGRADES: Dict[CompanyInfoTier, bool] = {
        CompanyInfoTier.PUBLIC_LARGE: False,      # No upgrade needed, lots of info available
        CompanyInfoTier.PUBLIC_MEDIUM: False,     # No upgrade needed
        CompanyInfoTier.PRIVATE_LIMITED: True,    # Upgrade to deeper models
        CompanyInfoTier.STARTUP_STEALTH: True,    # Upgrade to deeper models
    }
    
    def __init__(self, mode: ResearchMode = ResearchMode.QUICK):
        """
        Initialize the model selector.
        
        Args:
            mode: Research mode (quick or comprehensive).
        """
        self.mode = mode
        self.available_models = RESEARCH_MODE_MODELS[mode]
    
    def select_model(
        self,
        category: QueryCategory,
        info_tier: CompanyInfoTier = CompanyInfoTier.PUBLIC_MEDIUM,
        force_model: Optional[PerplexityModel] = None,
    ) -> ModelSelection:
        """
        Select the best model for a query.
        
        Args:
            category: Query category.
            info_tier: Company information availability tier.
            force_model: Override model selection.
        
        Returns:
            ModelSelection with model and reasoning.
        """
        if force_model:
            return ModelSelection(
                model=force_model,
                reason="Forced model selection",
                estimated_cost=self._estimate_query_cost(force_model),
            )
        
        # Get base model for category and mode
        base_model = self.CATEGORY_MODELS.get(category, {}).get(
            self.mode, PerplexityModel.SONAR
        )
        
        # Check if model is available in current mode
        if base_model not in self.available_models:
            base_model = self.available_models[0]
        
        # Apply tier adjustments for comprehensive mode
        selected_model = base_model
        reason = f"Default model for {category.value} in {self.mode.value} mode"
        
        # Note: previously, COMPREHENSIVE mode upgraded private/stealth companies
        # to SONAR_DEEP_RESEARCH here. That model autonomously chains many web
        # searches and emits long outputs + reasoning tokens, costing $1-5 per
        # call. It was making "comprehensive" runs cost $6-15 instead of the
        # advertised sub-dollar range, so the upgrade path is disabled.
        
        # Determine fallback
        fallback = PerplexityModel.SONAR if selected_model != PerplexityModel.SONAR else None
        
        return ModelSelection(
            model=selected_model,
            reason=reason,
            estimated_cost=self._estimate_query_cost(selected_model),
            fallback_model=fallback,
        )
    
    def select_models_for_research(
        self,
        categories: List[QueryCategory],
        info_tier: CompanyInfoTier = CompanyInfoTier.PUBLIC_MEDIUM,
    ) -> Dict[QueryCategory, ModelSelection]:
        """
        Select models for multiple query categories.
        
        Args:
            categories: List of query categories.
            info_tier: Company information tier.
        
        Returns:
            Dict mapping category to model selection.
        """
        return {
            category: self.select_model(category, info_tier)
            for category in categories
        }
    
    def estimate_total_cost(
        self,
        categories: List[QueryCategory],
        queries_per_category: int = 2,
    ) -> Dict[str, float]:
        """
        Estimate total cost for a research session.
        
        Args:
            categories: Query categories to research.
            queries_per_category: Average queries per category.
        
        Returns:
            Cost breakdown dict.
        """
        total = 0.0
        breakdown = {}
        
        for category in categories:
            selection = self.select_model(category)
            category_cost = selection.estimated_cost * queries_per_category
            breakdown[category.value] = round(category_cost, 4)
            total += category_cost
        
        return {
            "breakdown": breakdown,
            "total": round(total, 4),
            "mode": self.mode.value,
        }
    
    def _estimate_query_cost(
        self,
        model: PerplexityModel,
        input_tokens: int = 500,
        output_tokens: int = 1500,
    ) -> float:
        """Estimate cost for a single query."""
        input_cost, output_cost = PERPLEXITY_COSTS.get(model, (0.001, 0.001))
        return (input_tokens / 1000 * input_cost) + (output_tokens / 1000 * output_cost)
    
    def get_model_info(self, model: PerplexityModel) -> Dict[str, any]:
        """Get information about a model."""
        input_cost, output_cost = PERPLEXITY_COSTS.get(model, (0.001, 0.001))
        
        descriptions = {
            PerplexityModel.SONAR: "Fast, cost-effective for general searches",
            PerplexityModel.SONAR_PRO: "Higher quality results for complex queries",
            PerplexityModel.SONAR_REASONING: "Logical analysis and comparisons",
            PerplexityModel.SONAR_REASONING_PRO: "Complex technical analysis",
            PerplexityModel.SONAR_DEEP_RESEARCH: "Comprehensive multi-step research",
        }
        
        return {
            "model": model.value,
            "description": descriptions.get(model, "Unknown model"),
            "input_cost_per_1k": input_cost,
            "output_cost_per_1k": output_cost,
            "available_in_mode": model in self.available_models,
        }
