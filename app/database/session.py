from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings

url = make_url(settings.DATABASE_URL)

if url.drivername == "postgresql":
    url = url.set(drivername="postgresql+psycopg")

engine = create_engine(
    url,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)
