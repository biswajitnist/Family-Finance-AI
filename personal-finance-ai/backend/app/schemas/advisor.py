from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AdvisorForecast(BaseModel):
    expected_income: Decimal
    expected_expenses: Decimal
    expected_surplus: Decimal
    expected_month_end_balance: Decimal
    recurring_payment_impact: Decimal
    confidence_score: Decimal
    category_risks: list[dict]


class AdvisorRecommendation(BaseModel):
    id: int
    title: str
    description: str
    priority: str
    estimated_impact_amount: Decimal
    recommendation_type: str
    explanation: str
    related_data: dict
    status: str


class AdvisorAlert(BaseModel):
    id: int
    alert_type: str
    severity: str
    message: str
    reason: str
    recommended_action: str
    status: str
    transactions: list[dict]


class AdvisorDashboard(BaseModel):
    month: str
    summary_sentence_1: str
    summary_sentence_2: str
    explanation: str
    confidence_score: Decimal
    generated_at: datetime
    local_ai_used: bool
    source_basis: list[str]
    financial_position: dict[str, Decimal]
    forecast: AdvisorForecast
    recommendations: list[AdvisorRecommendation]
    alerts: list[AdvisorAlert]


class AdvisorStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|dismissed|completed|resolved)$")
