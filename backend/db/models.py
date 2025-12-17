from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    DateTime,
    JSON,
    UniqueConstraint,
    ForeignKey,
    Float,
)
from sqlalchemy.orm import declarative_base, relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()
EASTERN_TZ = ZoneInfo("America/New_York")


def now_eastern():
    """Return a timezone-aware timestamp in US/Eastern."""
    return datetime.now(EASTERN_TZ)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255))
    location = Column(String(255))
    description = Column(Text)
    source_url = Column(Text, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_eastern)
    match_score = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("source_url", name="uq_job_source_url"),
    )

    application_packages = relationship(
        "ApplicationPackage",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    generated_artifacts = relationship(
        "GeneratedArtifact",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    job_embedding = relationship(
        "JobEmbedding",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Job(title={self.title}, company={self.company}, location={self.location})>"


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), default="text")  # text, pdf, image, code
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536))  # 1536-dim for OpenAI text embeddings
    source = Column(String(255))
    artifact_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_eastern)

    def __repr__(self):
        return f"<Artifact(name={self.name}, type={self.type}, source={self.source})>"


class GeneratedArtifact(Base):
    __tablename__ = "generated_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    job_title = Column(String(255), nullable=False)
    company = Column(String(255))
    artifact_type = Column(String(50))  # e.g. "resume" or "cover_letter"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_eastern)

    job = relationship("Job", back_populates="generated_artifacts")


class JobEmbedding(Base):
    __tablename__ = "job_embeddings"

    job_id = Column(Integer, ForeignKey("jobs.id"), primary_key=True)
    embedding = Column(Vector(1536), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_eastern)
    updated_at = Column(
        DateTime(timezone=True),
        default=now_eastern,
        onupdate=now_eastern,
    )

    job = relationship("Job", back_populates="job_embedding")


class ApplicationPackage(Base):
    __tablename__ = "application_packages"

    id = Column(Integer, primary_key=True, autoincrement=True)

    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    title = Column(String)
    company = Column(String)
    score = Column(String)

    resume_path = Column(String)        # path to saved PDF
    cover_letter_path = Column(String)  # path to saved PDF

    package_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_eastern)

    job = relationship("Job", back_populates="application_packages")
