"""
Initialize the Chainlit SQLAlchemy database with required tables.
Run this script once before starting the app to create the necessary tables.
"""
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# SQL schema for Chainlit data layer tables (complete schema matching Chainlit's expectations)
SCHEMA = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    identifier TEXT UNIQUE NOT NULL,
    createdAt TEXT,
    metadata TEXT
);

-- Threads table  
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    name TEXT,
    userId TEXT,
    userIdentifier TEXT,
    createdAt TEXT,
    tags TEXT,
    metadata TEXT,
    FOREIGN KEY (userId) REFERENCES users(id)
);

-- Steps table
CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY,
    threadId TEXT,
    parentId TEXT,
    name TEXT,
    type TEXT,
    streaming BOOLEAN,
    input TEXT,
    output TEXT,
    isError BOOLEAN,
    createdAt TEXT,
    start TEXT,
    "end" TEXT,
    defaultOpen BOOLEAN,
    showInput TEXT,
    metadata TEXT,
    generation TEXT,
    waitForAnswer BOOLEAN,
    tags TEXT,
    language TEXT,
    FOREIGN KEY (threadId) REFERENCES threads(id)
);

-- Elements table (with all required columns)
CREATE TABLE IF NOT EXISTS elements (
    id TEXT PRIMARY KEY,
    threadId TEXT,
    stepId TEXT,
    name TEXT,
    type TEXT,
    display TEXT,
    language TEXT,
    size TEXT,
    page INTEGER,
    url TEXT,
    objectKey TEXT,
    forId TEXT,
    mime TEXT,
    autoPlay BOOLEAN,
    playerConfig TEXT,
    chainlitKey TEXT,
    props TEXT,
    FOREIGN KEY (threadId) REFERENCES threads(id),
    FOREIGN KEY (stepId) REFERENCES steps(id)
);

-- Feedback table
CREATE TABLE IF NOT EXISTS feedbacks (
    id TEXT PRIMARY KEY,
    threadId TEXT,
    forId TEXT,
    value INTEGER,
    strategy TEXT,
    comment TEXT,
    createdAt TEXT,
    FOREIGN KEY (threadId) REFERENCES threads(id),
    FOREIGN KEY (forId) REFERENCES steps(id)
);
"""

async def init_db():
    """Initialize the database with required tables."""
    # Delete old database file to start fresh with correct schema
    if os.path.exists("conversations.db"):
        os.remove("conversations.db")
        print("Removed old database file.")
    
    engine = create_async_engine("sqlite+aiosqlite:///conversations.db")
    
    async with engine.begin() as conn:
        for statement in SCHEMA.split(';'):
            statement = statement.strip()
            if statement:
                await conn.execute(text(statement))
    
    await engine.dispose()
    print("✅ Database initialized successfully!")
    print("Tables created: users, threads, steps, elements, feedbacks")

if __name__ == "__main__":
    asyncio.run(init_db())
