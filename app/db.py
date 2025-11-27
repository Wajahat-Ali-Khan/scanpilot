from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

# Determine if we're using SQLite
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# Configure engine with appropriate settings based on database type
if is_sqlite:
    # SQLite doesn't support connection pooling
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,  # Set to True for SQL query logging in development
        future=True,
    )
else:
    # PostgreSQL/MySQL with connection pooling
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,  # Set to True for SQL query logging in development
        future=True,
        pool_size=10,  # Maximum number of connections to keep in the pool
        max_overflow=20,  # Maximum number of connections that can be created beyond pool_size
        pool_pre_ping=True,  # Verify connections before using them
        pool_recycle=3600,  # Recycle connections after 1 hour
    )

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,  # Manual control over flushing
    autocommit=False,  # Explicit transaction control
)

Base = declarative_base()


async def get_db() -> AsyncSession:
    """
    Dependency to get database session.
    
    Provides a request-scoped database session that is automatically
    closed after the request completes.
    
    Yields:
        AsyncSession: Database session
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)