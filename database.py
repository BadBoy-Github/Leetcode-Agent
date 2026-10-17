import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, DateTime, inspect, desc
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

load_dotenv()

Base = declarative_base()

class SolvedQuestion(Base):
    __tablename__ = "solved_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    frontend_id = Column(String(20), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    title_slug = Column(String(255), index=True, nullable=False)
    difficulty = Column(String(20), nullable=False)  # Easy, Medium, Hard
    language = Column(String(20), nullable=False)    # python3, java
    code = Column(Text, nullable=False)
    status = Column(String(50), default="Accepted")
    runtime = Column(String(50), default="N/A")
    memory = Column(String(50), default="N/A")
    runtime_percentile = Column(Float, nullable=True)
    memory_percentile = Column(Float, nullable=True)
    submission_id = Column(String(50), nullable=True)
    steps_count = Column(Integer, default=1)
    solved_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "frontend_id": self.frontend_id,
            "title": self.title,
            "title_slug": self.title_slug,
            "difficulty": self.difficulty,
            "language": self.language,
            "code": self.code,
            "status": self.status,
            "runtime": self.runtime,
            "memory": self.memory,
            "runtime_percentile": self.runtime_percentile,
            "memory_percentile": self.memory_percentile,
            "submission_id": self.submission_id,
            "steps_count": self.steps_count,
            "solved_at": self.solved_at.strftime("%Y-%m-%d %H:%M:%S") if self.solved_at else "",
            "notes": self.notes,
            "url": f"https://leetcode.com/problems/{self.title_slug}/",
        }


class DatabaseManager:
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.getenv("DATABASE_URL", "").strip()
        self.engine = None
        self.Session = None
        self.is_postgres = False
        self.connection_error = None
        self._init_connection()

    def _normalize_url(self, raw_url: str) -> str:
        url = raw_url.strip()
        if not url:
            return ""
        # Handle postgres:// and postgresql:// to use psycopg2
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://"):]
        elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = "postgresql+psycopg2://" + url[len("postgresql://"):]
        
        # If neon or supabase url without sslmode, add sslmode=require
        if ("neon.tech" in url or "supabase.co" in url) and "sslmode" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}sslmode=require"
            
        return url

    def _init_connection(self):
        normalized = self._normalize_url(self.db_url) if self.db_url else ""
        
        if normalized and (normalized.startswith("postgresql://") or normalized.startswith("postgresql+psycopg2://")):
            try:
                engine = create_engine(
                    normalized,
                    pool_pre_ping=True,
                    pool_recycle=300,
                    connect_args={"connect_timeout": 10}
                )
                # Verify connection
                with engine.connect() as conn:
                    pass
                self.engine = engine
                self.is_postgres = True
                self.connection_error = None
            except Exception as e:
                self.connection_error = str(e)
                # Fallback to local SQLite if PostgreSQL fails
                self._fallback_sqlite()
        else:
            self._fallback_sqlite()

        Base.metadata.create_all(self.engine)
        self.Session = scoped_session(sessionmaker(bind=self.engine))

    def _fallback_sqlite(self):
        sqlite_url = "sqlite:///leetcode_records.db"
        self.engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
        self.is_postgres = False

    def test_connection(self) -> Dict[str, Any]:
        """Test current database connection and return status information."""
        try:
            with self.engine.connect() as conn:
                dialect = self.engine.dialect.name
                return {
                    "success": True,
                    "dialect": dialect,
                    "is_postgres": self.is_postgres,
                    "message": "Connected successfully to " + ("PostgreSQL (Neon / Supabase)" if self.is_postgres else "Local SQLite fallback")
                }
        except Exception as e:
            return {
                "success": False,
                "dialect": "unknown",
                "is_postgres": False,
                "message": f"Connection error: {str(e)}"
            }

    def save_solution(
        self,
        frontend_id: str,
        title: str,
        title_slug: str,
        difficulty: str,
        language: str,
        code: str,
        status: str = "Accepted",
        runtime: str = "N/A",
        memory: str = "N/A",
        runtime_percentile: Optional[float] = None,
        memory_percentile: Optional[float] = None,
        submission_id: Optional[str] = None,
        steps_count: int = 1,
        notes: Optional[str] = None,
    ) -> SolvedQuestion:
        session = self.Session()
        try:
            # Check if this question is already recorded
            existing = session.query(SolvedQuestion).filter(
                (SolvedQuestion.title_slug == title_slug) & (SolvedQuestion.language == language)
            ).first()

            if existing:
                existing.code = code
                existing.status = status
                existing.runtime = runtime
                existing.memory = memory
                existing.runtime_percentile = runtime_percentile
                existing.memory_percentile = memory_percentile
                existing.submission_id = str(submission_id) if submission_id else existing.submission_id
                existing.steps_count = steps_count
                existing.solved_at = datetime.utcnow()
                existing.notes = notes or existing.notes
                target = existing
            else:
                target = SolvedQuestion(
                    frontend_id=str(frontend_id),
                    title=title,
                    title_slug=title_slug,
                    difficulty=difficulty.capitalize(),
                    language=language,
                    code=code,
                    status=status,
                    runtime=runtime,
                    memory=memory,
                    runtime_percentile=runtime_percentile,
                    memory_percentile=memory_percentile,
                    submission_id=str(submission_id) if submission_id else None,
                    steps_count=steps_count,
                    notes=notes,
                    solved_at=datetime.utcnow()
                )
                session.add(target)
            
            session.commit()
            session.refresh(target)
            return target
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_all_solved(self, difficulty: Optional[str] = None, language: Optional[str] = None) -> List[Dict[str, Any]]:
        session = self.Session()
        try:
            query = session.query(SolvedQuestion)
            if difficulty and difficulty != "All":
                query = query.filter(SolvedQuestion.difficulty == difficulty.capitalize())
            if language and language != "All":
                query = query.filter(SolvedQuestion.language == language)
            
            results = query.order_by(desc(SolvedQuestion.solved_at)).all()
            return [r.to_dict() for r in results]
        finally:
            session.close()

    def is_solved(self, title_slug: str) -> bool:
        session = self.Session()
        try:
            count = session.query(SolvedQuestion).filter(SolvedQuestion.title_slug == title_slug).count()
            return count > 0
        finally:
            session.close()

    def get_solved_slugs(self) -> set:
        session = self.Session()
        try:
            rows = session.query(SolvedQuestion.title_slug).all()
            return {r[0] for r in rows}
        finally:
            session.close()

    def get_stats(self) -> Dict[str, Any]:
        session = self.Session()
        try:
            all_q = session.query(SolvedQuestion).all()
            easy = sum(1 for q in all_q if q.difficulty.lower() == "easy")
            medium = sum(1 for q in all_q if q.difficulty.lower() == "medium")
            hard = sum(1 for q in all_q if q.difficulty.lower() == "hard")

            # Per-language breakdown
            lang_counts: Dict[str, int] = {}
            for q in all_q:
                lang = q.language.lower()
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

            return {
                "total": len(all_q),
                "easy": easy,
                "medium": medium,
                "hard": hard,
                "python": lang_counts.get("python3", 0) + lang_counts.get("python", 0),
                "java": lang_counts.get("java", 0),
                "other": max(0, len(all_q) - lang_counts.get("python3", 0) - lang_counts.get("python", 0) - lang_counts.get("java", 0)),
                "lang_breakdown": lang_counts,
            }
        finally:
            session.close()

    def delete_solution(self, item_id: int) -> bool:
        session = self.Session()
        try:
            item = session.query(SolvedQuestion).filter(SolvedQuestion.id == item_id).first()
            if item:
                session.delete(item)
                session.commit()
                return True
            return False
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()

# Singleton helper
_db_manager = None

def get_db(db_url: Optional[str] = None) -> DatabaseManager:
    global _db_manager
    if _db_manager is None or (db_url and db_url != _db_manager.db_url):
        _db_manager = DatabaseManager(db_url)
    return _db_manager
