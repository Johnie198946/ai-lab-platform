"""Tenant-scoped dataset, model, topology, and telemetry registry for AI Resource.

Large artifacts and row data live in object storage or an external table engine. These
tables keep durable metadata, immutable versions, lineage, bindings, and audit-friendly
configuration in PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class WorkspaceDataset(Base):
    __tablename__ = "workspace_datasets"
    __table_args__ = (UniqueConstraint("tenant_key", "project_id", "name", name="uq_workspace_dataset_project_name"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    dataset_type: Mapped[str] = mapped_column(String(32), default="synthetic", index=True)
    truth_status: Mapped[str] = mapped_column(String(24), default="SYNTHETIC", index=True)
    lifecycle_stage: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    active_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tags: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkspaceDatasetVersion(Base):
    __tablename__ = "workspace_dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_workspace_dataset_version"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("workspace_datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    digest: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    schema: Mapped[list] = mapped_column(JSON, default=list)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    splits: Mapped[list] = mapped_column(JSON, default=list)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    lineage: Mapped[dict] = mapped_column(JSON, default=dict)
    generation_manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    byte_size: Mapped[int] = mapped_column(BigInteger, default=0)
    object_uri: Mapped[str] = mapped_column(Text, default="")
    storage_format: Mapped[str] = mapped_column(String(24), default="parquet")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceDatasetArtifact(Base):
    __tablename__ = "workspace_dataset_artifacts"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("workspace_dataset_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    split: Mapped[str] = mapped_column(String(32), default="all")
    object_uri: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(80), default="application/x-parquet")
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    byte_size: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceDatasetUsage(Base):
    __tablename__ = "workspace_dataset_usages"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("workspace_dataset_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    consumer_type: Mapped[str] = mapped_column(String(32), nullable=False)
    consumer_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(32), default="simulation")
    binding: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceModel(Base):
    __tablename__ = "workspace_models"
    __table_args__ = (UniqueConstraint("tenant_key", "project_id", "name", name="uq_workspace_model_project_name"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    model_type: Mapped[str] = mapped_column(String(32), default="llm")
    delivery_mode: Mapped[str] = mapped_column(String(24), default="online", index=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[dict] = mapped_column(JSON, default=dict)
    active_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkspaceModelVersion(Base):
    __tablename__ = "workspace_model_versions"
    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_workspace_model_version"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("workspace_models.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(48), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, default="")
    artifact_uri: Mapped[str] = mapped_column(Text, default="")
    digest: Mapped[str] = mapped_column(String(80), nullable=False)
    lifecycle_stage: Mapped[str] = mapped_column(String(24), default="candidate", index=True)
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    runtime: Mapped[dict] = mapped_column(JSON, default=dict)
    serving: Mapped[dict] = mapped_column(JSON, default=dict)
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict)
    lineage: Mapped[dict] = mapped_column(JSON, default=dict)
    license: Mapped[str] = mapped_column(String(80), default="")
    risk: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceTopologyNode(Base):
    __tablename__ = "workspace_topology_nodes"
    __table_args__ = (UniqueConstraint("project_id", "node_key", name="uq_workspace_topology_node_key"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    node_key: Mapped[str] = mapped_column(String(80), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    truth_status: Mapped[str] = mapped_column(String(24), default="PLANNED")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    resource_binding: Mapped[dict] = mapped_column(JSON, default=dict)
    model_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    dataset_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    position: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkspaceTelemetryBinding(Base):
    __tablename__ = "workspace_telemetry_bindings"
    __table_args__ = (UniqueConstraint("topology_node_id", "metric_key", name="uq_workspace_telemetry_node_metric"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    topology_node_id: Mapped[str] = mapped_column(ForeignKey("workspace_topology_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(48), default="canonical")
    query: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(24), default="")
    thresholds: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
