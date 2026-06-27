import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FilterOperator = Literal[
    "equals",
    "not_equals",
    "contains",
    "greater_than",
    "less_than",
    "between",
    "date_range",
    "is_empty",
    "is_not_empty",
]
AggregationFunction = Literal[
    "sum",
    "average",
    "count",
    "minimum",
    "maximum",
    "opening_balance",
    "closing_balance",
    "net_change",
]
ChartType = Literal[
    "table",
    "bar",
    "line",
    "pie",
    "donut",
    "area",
    "stacked_bar",
    "grouped_bar",
    "horizontal_bar",
    "kpi",
    "trend",
]


class ReportFilter(BaseModel):
    field: str
    operator: FilterOperator
    value: Any = None


class ReportAggregation(BaseModel):
    field: str
    function: AggregationFunction


class ReportSort(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "asc"


class ReportChart(BaseModel):
    type: ChartType = "table"
    xAxis: str | None = None
    yAxis: str | None = None
    showLegend: bool = True
    showDataLabels: bool = False
    showTable: bool = False
    showFilters: bool = True


class ReportConfig(BaseModel):
    fields: list[str] = Field(min_length=1)
    filters: list[ReportFilter] = []
    groupBy: list[str] = []
    aggregation: ReportAggregation | None = None
    sort: ReportSort | None = None
    limit: int = Field(default=100, ge=1, le=500)
    chart: ReportChart = ReportChart()

    @model_validator(mode="after")
    def validate_chart(self) -> "ReportConfig":
        if self.chart.type != "table" and not self.chart.xAxis:
            raise ValueError("Choose an X-axis for chart reports.")
        if self.chart.type != "table" and not self.chart.yAxis:
            raise ValueError("Choose a Y-axis for chart reports.")
        return self


class CustomReportCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    data_source: str
    chart_type: ChartType
    config_json: ReportConfig
    dashboard_section: str | None = None
    widget_size: str | None = None
    widget_position: int | None = None
    schedule_frequency: str | None = None


class CustomReportRead(CustomReportCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None

    @field_validator("config_json", mode="before")
    @classmethod
    def load_config_json(cls, value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value


class ReportPreviewRequest(BaseModel):
    data_source: str
    chart_type: ChartType
    config_json: ReportConfig


class ReportResult(BaseModel):
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]
    total_rows: int
    chart_type: ChartType
    x_axis: str | None = None
    y_axis: str | None = None
    value: Any = None
    subtitle: str | None = None


class ReportMetadata(BaseModel):
    data_sources: list[dict[str, Any]]
    chart_types: list[dict[str, str]]
    filter_operators: list[dict[str, str]]
    aggregations: list[dict[str, str]]
    dashboard_sections: list[dict[str, str]]
    widget_sizes: list[dict[str, str]]
    schedule_frequencies: list[dict[str, str]]


class DashboardWidgetRequest(BaseModel):
    section: str = "Overview"
    widget_size: str = "medium"
    position: int = 100


class ReportScheduleRequest(BaseModel):
    frequency: str | None = None


class AIAssistedReportRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)
