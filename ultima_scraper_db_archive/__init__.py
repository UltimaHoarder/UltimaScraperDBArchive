"""Primary database model exports for UltimaScraper.

Package-level imports should resolve to the active PostgreSQL-backed models.
The legacy sqlite ``site.py`` module is retained only for compatibility helpers
such as ``DEFAULT_DB_PATH``.
"""

from __future__ import annotations

from pathlib import Path

from .databases.ultima_archive.schemas.templates.postgres_site import (
    BackendInventoryModel,
    BoughtContentModel,
    CentralJobModel,
    CentralTaskModel,
    ContentMediaAssoModel,
    ContentMentionModel,
    DRMManifestModel,
    FavoriteUserModel,
    FilePathModel,
    HistoUserInfoModel,
    InvalidUserModel,
    LinkedPostModel,
    LinkedUserModel,
    MassMessageModel,
    MediaModel,
    MessageModel,
    PostModel,
    ProxyGeolocationModel,
    RemoteURLModel,
    SearchLoadoutModel,
    SettingsModel,
    SiteTemplate,
    SocialModel,
    StatisticsModel,
    StoryModel,
    SubscriptionModel,
    UserAliasModel,
    UserAuthModel,
    UserInfoModel,
    UserModel,
    UserProfileMediaModel,
    WebsiteModel,
    content_types,
    utcnow,
)
from .module import MIGRATION_BUNDLE, ArchiveAPI, USDBArchiveModule

# Keep the historical SQLite filename so migration discovery still finds
# existing archives after the distribution/package rename.
DEFAULT_DB_PATH = Path.home() / ".ultima_scraper" / "ultima_scraper_mini.db"

# Backwards-compatible alias for older imports that expected JobModel at the
# package root. Central jobs now live in PostgreSQL management tables.
JobModel = CentralJobModel

__all__ = [
    "BackendInventoryModel",
    "BoughtContentModel",
    "CentralJobModel",
    "CentralTaskModel",
    "ContentMediaAssoModel",
    "ContentMentionModel",
    "content_types",
    "DEFAULT_DB_PATH",
    "DRMManifestModel",
    "FavoriteUserModel",
    "FilePathModel",
    "HistoUserInfoModel",
    "InvalidUserModel",
    "JobModel",
    "LinkedPostModel",
    "LinkedUserModel",
    "MassMessageModel",
    "MediaModel",
    "MessageModel",
    "PostModel",
    "ProxyGeolocationModel",
    "RemoteURLModel",
    "SearchLoadoutModel",
    "SettingsModel",
    "SiteTemplate",
    "SocialModel",
    "StoryModel",
    "StatisticsModel",
    "SubscriptionModel",
    "UserAliasModel",
    "UserAuthModel",
    "UserInfoModel",
    "UserModel",
    "UserProfileMediaModel",
    "utcnow",
    "WebsiteModel",
    "ArchiveAPI",
    "MIGRATION_BUNDLE",
    "USDBArchiveModule",
]
