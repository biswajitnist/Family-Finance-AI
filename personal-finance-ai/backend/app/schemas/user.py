from pydantic import BaseModel, ConfigDict, Field


class UserProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = None
    base_currency: str = Field(min_length=3, max_length=3)
    country: str = Field(min_length=2, max_length=2)
    timezone: str = "Europe/Berlin"
    preferred_language: str = "en"
    tax_country: str = "DE"
    date_format: str = "DD-MM-YYYY"
    number_format: str = "1.234,56"
    financial_year_start: str = "01-01"
    default_portfolio_view: str = "overview"
    default_refresh_frequency: str = "hourly"
    setup_completed: bool = True


class UserProfileRead(UserProfileUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: int
