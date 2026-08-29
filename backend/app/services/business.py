from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import pandas as pd
from sqlalchemy.orm import Session

from backend.app.services.analytics import SalesAnalytics, sales_frame
from backend.app.services.filtering import SalesFilters
from backend.app.services.machine_learning import MachineLearningService


@dataclass
class BusinessIntelligence:
    """Request-scoped facade that loads the database snapshot only once."""

    session: Session
    filters: SalesFilters | None = None

    @cached_property
    def frame(self) -> pd.DataFrame:
        return sales_frame(self.session, self.filters)

    @cached_property
    def analytics(self) -> SalesAnalytics:
        return SalesAnalytics(self.frame)

    @cached_property
    def machine_learning(self) -> MachineLearningService:
        return MachineLearningService(self.frame)
