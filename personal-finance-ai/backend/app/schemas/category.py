from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_category_id: int | None = None
    type: str = Field(pattern="^(income|expense|transfer)$")
    icon: str = Field(default="category", max_length=40)
    color: str = Field(default="green", max_length=20)


class CategoryRead(CategoryCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)
