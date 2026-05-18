import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Text,
)

# THIS is the modern way to use declarative_base in SQLAlchemy 2.0
# The old way (declarative_base from ext.declarative) still works
# but throws a deprecation warning — this fixes that warning
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

Base = declarative_base()


class PipelineFailure(Base):
    __tablename__ = "pipeline_failures"

    id = Column(Integer, primary_key=True, index=True)
    repository = Column(String(255), nullable=False, index=True)
    workflow = Column(String(255), nullable=True)
    run_id = Column(String(100), nullable=True, index=True)
    branch = Column(String(255), nullable=True, index=True)
    commit_sha = Column(String(100), nullable=True)
    s3_key = Column(String(500), nullable=True)
    status = Column(String(50), default="pending_analysis", index=True)
    root_cause = Column(Text, nullable=True)
    suggested_fix = Column(Text, nullable=True)
    failure_category = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime, nullable=True)
    stored_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "repository": self.repository,
            "workflow": self.workflow,
            "run_id": self.run_id,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "s3_key": self.s3_key,
            "status": self.status,
            "root_cause": self.root_cause,
            "suggested_fix": self.suggested_fix,
            "failure_category": self.failure_category,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "stored_at": self.stored_at.isoformat() if self.stored_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }


def get_engine():
    # THIS is the key fix — we create the engine LAZILY
    # meaning only when a function actually needs it
    # NOT at import time
    # Before: engine = create_engine(DATABASE_URL) ran at the top of the file
    # the moment ANY file imported database.py, it tried to connect to postgres
    # Now: engine is only created when get_engine() is actually called
    # During tests, the mock intercepts before get_engine() is ever reached
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set")
    return create_engine(DATABASE_URL, echo=False)


def get_session():
    # Creates a new database session using the lazy engine
    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def create_tables():
    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine, checkfirst=True)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create tables: {str(e)}")
        raise


def save_failure_to_db(parsed_data: dict) -> int:
    session = get_session()

    try:
        def parse_dt(dt_string):
            if not dt_string or dt_string == "unknown":
                return None
            try:
                return datetime.strptime(dt_string, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                try:
                    return datetime.fromisoformat(dt_string.replace("Z", ""))
                except Exception:
                    return None

        failure = PipelineFailure(
            repository=parsed_data.get("repository", "unknown"),
            workflow=parsed_data.get("workflow", "unknown"),
            run_id=str(parsed_data.get("run_id", "unknown")),
            branch=parsed_data.get("branch", "unknown"),
            commit_sha=parsed_data.get("commit_sha", "unknown"),
            s3_key=parsed_data.get("s3_key", "unknown"),
            status=parsed_data.get("status", "pending_analysis"),
            root_cause=parsed_data.get("root_cause"),
            suggested_fix=parsed_data.get("suggested_fix"),
            failure_category=parsed_data.get("failure_category"),
            created_at=parse_dt(parsed_data.get("created_at")),
            stored_at=parse_dt(parsed_data.get("stored_at")),
        )

        session.add(failure)
        session.commit()
        session.refresh(failure)

        logger.info(f"Saved failure to DB with id: {failure.id}")
        return failure.id

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to save failure to DB: {str(e)}")
        raise

    finally:
        session.close()


def get_recent_failures(limit: int = 10) -> list:
    session = get_session()
    try:
        failures = session.query(PipelineFailure)\
            .order_by(PipelineFailure.processed_at.desc())\
            .limit(limit)\
            .all()
        return [f.to_dict() for f in failures]

    except Exception as e:
        logger.error(f"Failed to retrieve failures: {str(e)}")
        return []

    finally:
        session.close()