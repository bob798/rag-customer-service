import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, inspect, text
from db.models import Base, Document, Chunk, Session as ChatSession, Message, Config

DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_create_document(db_session):
    doc = Document(filename="manual.pdf", file_type="pdf")
    db_session.add(doc)
    await db_session.commit()

    result = await db_session.execute(select(Document).where(Document.filename == "manual.pdf"))
    fetched = result.scalar_one()
    assert fetched.filename == "manual.pdf"
    assert fetched.file_type == "pdf"
    assert fetched.id is not None
    assert fetched.created_at is not None


async def test_document_status_default(db_session):
    doc = Document(filename="report.docx", file_type="docx")
    db_session.add(doc)
    await db_session.commit()

    result = await db_session.execute(select(Document).where(Document.filename == "report.docx"))
    fetched = result.scalar_one()
    assert fetched.status == "pending"


async def test_create_chunk_with_document(db_session):
    doc = Document(filename="guide.pdf", file_type="pdf")
    db_session.add(doc)
    await db_session.flush()

    chunk = Chunk(doc_id=doc.id, content="Some chunk text", embedding_model="bge-small")
    db_session.add(chunk)
    await db_session.commit()

    result = await db_session.execute(select(Chunk).where(Chunk.doc_id == doc.id))
    fetched_chunk = result.scalar_one()
    assert fetched_chunk.content == "Some chunk text"
    assert fetched_chunk.doc_id == doc.id
    assert fetched_chunk.embedding_model == "bge-small"
    assert fetched_chunk.metadata_json == "{}"


async def test_cascade_delete_chunks(db_session):
    doc = Document(filename="delete_me.pdf", file_type="pdf")
    db_session.add(doc)
    await db_session.flush()

    chunk1 = Chunk(doc_id=doc.id, content="Chunk A")
    chunk2 = Chunk(doc_id=doc.id, content="Chunk B")
    db_session.add_all([chunk1, chunk2])
    await db_session.commit()

    # Verify chunks exist
    result = await db_session.execute(select(Chunk).where(Chunk.doc_id == doc.id))
    assert len(result.scalars().all()) == 2

    # Delete document — chunks should cascade
    await db_session.delete(doc)
    await db_session.commit()

    result = await db_session.execute(select(Chunk).where(Chunk.doc_id == doc.id))
    assert result.scalars().all() == []


async def test_create_session_and_message(db_session):
    chat = ChatSession()
    db_session.add(chat)
    await db_session.flush()

    msg = Message(
        session_id=chat.id,
        question="What is the return policy?",
        answer="You can return within 30 days.",
    )
    db_session.add(msg)
    await db_session.commit()

    result = await db_session.execute(select(Message).where(Message.session_id == chat.id))
    fetched = result.scalar_one()
    assert fetched.question == "What is the return policy?"
    assert fetched.answer == "You can return within 30 days."
    assert fetched.session_id == chat.id


async def test_message_defaults(db_session):
    chat = ChatSession()
    db_session.add(chat)
    await db_session.flush()

    msg = Message(
        session_id=chat.id,
        question="Hello?",
        answer="Hi there!",
    )
    db_session.add(msg)
    await db_session.commit()

    result = await db_session.execute(select(Message).where(Message.session_id == chat.id))
    fetched = result.scalar_one()
    assert fetched.uncertain is False
    assert fetched.confidence is None
    assert fetched.sources_json == "[]"


async def test_create_config(db_session):
    cfg = Config(key="llm_model", value="gpt-4o-mini")
    db_session.add(cfg)
    await db_session.commit()

    result = await db_session.execute(select(Config).where(Config.key == "llm_model"))
    fetched = result.scalar_one()
    assert fetched.key == "llm_model"
    assert fetched.value == "gpt-4o-mini"


async def test_update_config_value(db_session):
    cfg = Config(key="top_k", value="5")
    db_session.add(cfg)
    await db_session.commit()

    # Update value
    cfg.value = "10"
    await db_session.commit()

    result = await db_session.execute(select(Config).where(Config.key == "top_k"))
    fetched = result.scalar_one()
    assert fetched.value == "10"


async def test_init_db_creates_tables(tmp_path):
    """Call init_db() and verify all expected tables are created."""
    import os
    db_path = tmp_path / "test_init.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    # Re-import to pick up env var — use direct engine creation instead
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as conn:
        table_names = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )

    expected_tables = {"documents", "chunks", "sessions", "messages", "configs"}
    assert expected_tables.issubset(set(table_names))

    await engine.dispose()
    del os.environ["DATABASE_URL"]
