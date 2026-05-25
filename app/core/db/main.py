from __future__ import annotations

from app.core.db.categories import DatabaseCategoryMixin
from app.core.db.connection import DatabaseConnectionMixin
from app.core.db.llm import DatabaseLlmMixin
from app.core.db.maintenance import DatabaseMaintenanceMixin
from app.core.db.posts import DatabasePostMixin
from app.core.db.schema import DatabaseSchemaMixin
from app.core.db.settings import DatabaseSettingsMixin
from app.core.db.tags import DatabaseTagMixin


class Database(
    DatabaseConnectionMixin,
    DatabaseSchemaMixin,
    DatabaseCategoryMixin,
    DatabasePostMixin,
    DatabaseTagMixin,
    DatabaseLlmMixin,
    DatabaseMaintenanceMixin,
    DatabaseSettingsMixin,
):
    """SQLite database facade assembled from focused operation mixins."""

    pass
