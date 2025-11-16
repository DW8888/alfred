from sqlalchemy import Column, String, Integer, Text, DateTime, JSON,UniqueConstraint,TIMESTAMP
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone 
from pgvector.sqlalchemy import Vector

Base = declarative_base()

# Generates tables in the database
class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255))
    location = Column(String(255))
    description = Column(Text)
    source_url = Column(Text, unique=True)   # ⬅ UNIQUE
    created_at = Column(TIMESTAMP)

    __table_args__ = (
        UniqueConstraint("source_url", name="uq_job_source_url"),
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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Artifact(name={self.name}, type={self.type}, source={self.source})>"
class GeneratedArtifact(Base):
    __tablename__ = "generated_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    job_title = Column(String(255), nullable=False)
    company = Column(String(255))
    artifact_type = Column(String(50))  # e.g. "resume" or "cover_letter"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ApplicationPackage(Base):
    __tablename__ = "application_packages"

    id = Column(Integer, primary_key=True, autoincrement=True)

    job_id = Column(Integer)
    title = Column(String)
    company = Column(String)
    score = Column(String)

    resume_path = Column(String)        # path to saved PDF
    cover_letter_path = Column(String)  # path to saved PDF

    package_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
