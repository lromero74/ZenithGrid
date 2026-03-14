"""
Add donations table and seed monthly goal setting.
"""
import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

MIGRATION_NAME = "add_donations_table"


async def run_migration(db):
    """Create donations table and seed donation_goal_monthly setting."""

    # Create donations table
    try:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS donations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                amount DOUBLE PRECISION NOT NULL,
                currency VARCHAR(10) NOT NULL DEFAULT 'USD',
                payment_method VARCHAR(50) NOT NULL,
                tx_reference VARCHAR(255),
                donor_name VARCHAR(100),
                notes TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                confirmed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                donation_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_donations_user_id ON donations(user_id)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_donations_status ON donations(status)"
        ))
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_donations_donation_date ON donations(donation_date)"
        ))
        logger.info("Created donations table")
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise
        logger.info("donations table already exists")

    # Seed monthly goal setting
    try:
        await db.execute(text("""
            INSERT INTO settings (key, value, value_type, description)
            VALUES ('donation_goal_monthly', '100', 'float', 'Monthly donation goal in USD')
            ON CONFLICT (key) DO NOTHING
        """))
        logger.info("Seeded donation_goal_monthly setting")
    except Exception as e:
        logger.info(f"donation_goal_monthly setting already exists or error: {e}")
