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
    description_embedding = Column(Vector(1536), nullable=True)

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
    prompt_experiments = relationship(
        "PromptExperiment",
        back_populates="job",
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
    prompt_experiments = relationship(
        "PromptExperiment",
        back_populates="generated_artifact",
        cascade="all, delete-orphan",
    )




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


class PromptExperiment(Base):
    __tablename__ = "prompt_experiments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    variant_name = Column(String(50), nullable=False)
    punctuality_score = Column(Float)
    tone_score = Column(Float)
    alignment_score = Column(Float)
    impact_score = Column(Float)
    credtail_score = Column(Float)
    total_score = Column(Float)
    judge_reasoning = Column(Text)
    generated_artifact_id = Column(Integer, ForeignKey("generated_artifacts.id"))
    created_at = Column(DateTime(timezone=True), default=now_eastern)

    __table_args__ = (
        UniqueConstraint("job_id", "variant_name", name="uq_prompt_experiment_job_variant"),
    )

    job = relationship("Job", back_populates="prompt_experiments")
    generated_artifact = relationship("GeneratedArtifact", back_populates="prompt_experiments")
