from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from loa_api.comparison import compare_budget_records
from loa_api.database import Base
from loa_api.schemas import ComparisonRequest


def test_comparison_refuses_missing_structured_evidence() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        result = compare_budget_records(
            db,
            ComparisonRequest(entity_type="program", code="2021", years=[2024, 2025]),
        )
    assert not result.comparable
    assert "2024" in result.reason
