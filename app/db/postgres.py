from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Boolean, DateTime, JSON
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"timeout": 3},
    pool_pre_ping=False,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="api")
    messages: Mapped[dict] = mapped_column(JSON, default=list)
    handoff: Mapped[bool] = mapped_column(Boolean, default=False)
    handoff_status: Mapped[str] = mapped_column(String(32), default="none")  # none/pending/accepted/resolved
    agent_id: Mapped[str] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


# ── Conversation CRUD ──

async def save_conversation(conv_id: str, user_id: str, channel: str, messages: list[dict], handoff: bool = False):
    async with async_session() as session:
        conv = await session.get(Conversation, conv_id)
        if conv:
            conv.messages = messages
            conv.handoff = handoff
            conv.updated_at = datetime.utcnow()
        else:
            conv = Conversation(
                id=conv_id,
                user_id=user_id,
                channel=channel,
                messages=messages,
                handoff=handoff,
            )
            session.add(conv)
        await session.commit()


async def get_pending_handoffs() -> list[dict]:
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Conversation).where(
                Conversation.handoff == True,
                Conversation.handoff_status == "pending"
            )
        )
        convs = result.scalars().all()
        return [
            {
                "id": c.id,
                "user_id": c.user_id,
                "channel": c.channel,
                "messages": c.messages,
                "created_at": c.updated_at.isoformat(),
            }
            for c in convs
        ]
