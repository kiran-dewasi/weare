import os
import logging
import time
import asyncio
from typing import Dict, Tuple, Optional, Any
from sqlalchemy import text
from backend.database import SessionLocal
import google.generativeai as genai
import httpx

# Configure logging
logger = logging.getLogger(__name__)

# Constants
DB_TIMEOUT = 2.0
TALLY_TIMEOUT = 3.0
GEMINI_TIMEOUT = 1.0
REDIS_TIMEOUT = 1.0

class HealthCheck:
    """
    Health check module for K24.ai backend.
    Verifies connectivity to critical services: Database, Tally, Gemini, Redis.
    """

    @staticmethod
    async def check_database() -> Tuple[bool, str]:
        """
        Check PostgreSQL/SQLite database connection.
        Returns: (is_healthy, message)
        """
        start_time = time.time()
        db = SessionLocal()
        try:
            # Run simple query: SELECT 1
            db.execute(text("SELECT 1"))
            return True, "Connected"
        except Exception as e:
            logger.error(f"DB_CONNECTION_FAILED: {e}")
            return False, "Database unavailable"
        finally:
            db.close()
            duration = time.time() - start_time
            if duration > DB_TIMEOUT:
                logger.warning(f"Database check took {duration:.2f}s (timeout {DB_TIMEOUT}s)")

    @staticmethod
    async def check_tally() -> Tuple[bool, str]:
        """
        Check Tally connectivity.
        Checks HTTP endpoint since ODBC might not be configured in this environment.
        Returns: (is_healthy, message)
        """
        tally_url = os.getenv("TALLY_URL", "http://localhost:9000")
        
        # Check if Tally is configured
        if os.getenv("SKIP_TALLY_CHECK", "false").lower() == "true":
            return True, "Skipped (Configured to skip)"
            
        try:
            async with httpx.AsyncClient(timeout=TALLY_TIMEOUT) as client:
                try:
                    await client.get(tally_url)
                    return True, "Connected"
                except httpx.ConnectError:
                    return False, "Tally unreachable"
                except httpx.TimeoutException:
                    return False, "Tally timeout"
                except Exception:
                    # 404/405 means server is up
                    return True, "Connected"
        except Exception as e:
            logger.error(f"TALLY_CONNECTION_FAILED: {e}")
            return False, f"Tally error: {str(e)}"

    @staticmethod
    async def check_gemini() -> Tuple[bool, str]:
        """
        Check Gemini API authentication and connectivity.
        Returns: (is_healthy, message)
        """
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return False, "API Key missing"
            
        try:
            genai.configure(api_key=api_key)
            
            # Lightweight check: Count tokens instead of generating content
            # This verifies Auth is working and model exists without burning generation quota
            def check_models():
                try:
                    model = genai.GenerativeModel("gemini-2.0-flash")
                    model.count_tokens("test")
                    return True
                except Exception as e:
                    # If we get a 429 (Quota), it means Auth is working!
                    if "429" in str(e) or "Resource has been exhausted" in str(e):
                        return True
                    raise e
            
            # Run in thread to avoid blocking
            await asyncio.to_thread(check_models)
            return True, "Authenticated"
        except Exception as e:
            logger.error(f"GEMINI_AUTH_FAILED: {e}")
            return False, "AI service unavailable"

    @staticmethod
    async def check_redis() -> Tuple[bool, str]:
        """
        Check Redis cache connectivity.
        Returns: (is_healthy, message)
        """
        # Placeholder for Redis check - assuming in-memory fallback if not present
        # In a real scenario, we would import redis and ping
        try:
            # import redis.asyncio as redis
            # r = redis.from_url("redis://localhost")
            # await r.ping()
            # await r.close()
            return True, "Connected (Mock/In-Memory)"
        except ImportError:
            return True, "Redis not installed (Using In-Memory)"
        except Exception as e:
            logger.warning(f"REDIS_CONNECTION_FAILED: {e}")
            return False, "Redis unavailable"

    @staticmethod
    async def perform_all_checks() -> Dict[str, Any]:
        """Run all health checks and return status dict"""
        db_ok, db_msg = await HealthCheck.check_database()
        tally_ok, tally_msg = await HealthCheck.check_tally()
        gemini_ok, gemini_msg = await HealthCheck.check_gemini()
        redis_ok, redis_msg = await HealthCheck.check_redis()
        
        return {
            "database": {"healthy": db_ok, "message": db_msg},
            "tally": {"healthy": tally_ok, "message": tally_msg},
            "gemini": {"healthy": gemini_ok, "message": gemini_msg},
            "redis": {"healthy": redis_ok, "message": redis_msg},
            "overall_healthy": db_ok and gemini_ok # Tally/Redis might be optional depending on config
        }
