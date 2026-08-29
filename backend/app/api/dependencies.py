from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.services.filtering import SalesFilters

DbSession = Annotated[Session, Depends(get_db)]


def get_sales_filters(
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    region: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    category: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    product: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
) -> SalesFilters:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400, detail="start_date must be on or before end_date."
        )
    return SalesFilters(
        start_date=start_date,
        end_date=end_date,
        region=region,
        category=category,
        product=product,
    )


SalesFilterParams = Annotated[SalesFilters, Depends(get_sales_filters)]
