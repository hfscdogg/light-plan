import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from app.config import settings


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Builder(Base):
    __tablename__ = "builders"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(200), nullable=False)
    company = Column(String(200), nullable=True)
    email = Column(String(254), unique=True, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    projects = relationship("Project", back_populates="builder")


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    builder_id = Column(String(36), ForeignKey("builders.id"), nullable=True)
    name = Column(String(200), nullable=False)
    address = Column(String(500), nullable=True)
    status = Column(String(20), default="draft")  # draft, parsing, parsed, assigned, exported
    tier = Column(String(10), default="better")  # good, better, best
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    builder = relationship("Builder", back_populates="projects")
    floor_plans = relationship("FloorPlan", back_populates="project", cascade="all, delete-orphan")


class FloorPlan(Base):
    __tablename__ = "floor_plans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    original_filename = Column(String(500), nullable=False)
    stored_path = Column(String(1000), nullable=False)
    file_type = Column(String(10), nullable=False)  # pdf, png, jpg
    page_count = Column(Integer, default=1)
    raw_parse_json = Column(Text, nullable=True)
    parsed_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="floor_plans")
    rooms = relationship("Room", back_populates="floor_plan", cascade="all, delete-orphan")


class Room(Base):
    __tablename__ = "rooms"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    floor_plan_id = Column(String(36), ForeignKey("floor_plans.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    room_type = Column(String(50), nullable=False)
    sqft = Column(Float, nullable=True)
    width_ft = Column(Float, nullable=True)
    length_ft = Column(Float, nullable=True)
    ceiling_height_ft = Column(Float, default=9.0)
    position_x = Column(Float, nullable=True)
    position_y = Column(Float, nullable=True)
    bbox_x1 = Column(Float, nullable=True)
    bbox_y1 = Column(Float, nullable=True)
    bbox_x2 = Column(Float, nullable=True)
    bbox_y2 = Column(Float, nullable=True)

    floor_plan = relationship("FloorPlan", back_populates="rooms")
    fixtures = relationship("Fixture", back_populates="room", cascade="all, delete-orphan")


class Fixture(Base):
    __tablename__ = "fixtures"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    room_id = Column(String(36), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    fixture_type = Column(String(50), nullable=False)
    product_sku = Column(String(100), nullable=True)
    product_desc = Column(String(300), nullable=True)
    msrp_range = Column(String(50), nullable=True)
    tier_product_line = Column(String(10), nullable=True)
    zone = Column(String(50), nullable=True)
    position_x = Column(Float, default=0.5)
    position_y = Column(Float, default=0.5)
    notes = Column(String(500), nullable=True, default="")
    is_prewire = Column(Boolean, default=False)

    room = relationship("Room", back_populates="fixtures")


class Template(Base):
    __tablename__ = "templates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    room_type = Column(String(50), nullable=False)
    tier = Column(String(10), nullable=False)
    rules_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
