import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
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
    confidence = Column(String(20), nullable=True)
    additional_context = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True)
    stored_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, default=datetime.utcnow)
    analyzed_at = Column(DateTime, nullable=True)

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
            "confidence": self.confidence,
            "additional_context": self.additional_context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "stored_at": self.stored_at.isoformat() if self.stored_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
        }


def get_engine():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set")
    return create_engine(DATABASE_URL, echo=False)


def get_session():
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


def update_failure_analysis(failure_id: int, ai_result: dict):
    # Updates an existing failure record with AI analysis results
    # Called after analyze_failure() returns results
    session = get_session()
    try:
        # Query the existing record by ID
        failure = session.query(PipelineFailure).filter(
            PipelineFailure.id == failure_id
        ).first()

        if not failure:
            logger.error(f"No failure found with id: {failure_id}")
            return

        # Update the AI fields
        failure.root_cause = ai_result.get("root_cause")
        failure.suggested_fix = ai_result.get("suggested_fix")
        failure.failure_category = ai_result.get("failure_category")
        failure.confidence = ai_result.get("confidence")
        failure.additional_context = ai_result.get("additional_context")
        failure.status = "analyzed"
        failure.analyzed_at = datetime.utcnow()

        session.commit()
        logger.info(f"Updated failure {failure_id} with AI analysis")

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to update failure analysis: {str(e)}")
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