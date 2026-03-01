"""
Database migration: Add RBAC tables (Groups, Roles, Permissions)

Creates:
- groups table
- roles table
- permissions table
- user_groups junction table
- group_roles junction table
- role_permissions junction table

Seeds:
- 4 built-in groups: System Owners, Administrators, Traders, Observers
- 4 built-in roles: super_admin, admin, trader, viewer
- 28 permissions (resource:action pairs)
- Role-permission assignments
- Group-role assignments
- Migrates existing users by is_superuser flag
"""

import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")

# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------

GROUPS_TABLE = """
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    description VARCHAR(255),
    is_system BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50) UNIQUE NOT NULL,
    description VARCHAR(255),
    is_system BOOLEAN DEFAULT 0,
    requires_mfa BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

PERMISSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    description VARCHAR(255)
)
"""

USER_GROUPS_TABLE = """
CREATE TABLE IF NOT EXISTS user_groups (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, group_id)
)
"""

GROUP_ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS group_roles (
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, role_id)
)
"""

ROLE_PERMISSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
)
"""

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

BUILT_IN_GROUPS = [
    ("System Owners", "System owner(s). Full access to everything.", 1),
    ("Administrators", "System administrators. Manage users, groups, RBAC, settings.", 1),
    ("Traders", "Active traders. Full trading access, manage own bots/positions.", 1),
    ("Observers", "Read-only observers. Can view but not modify.", 1),
]

BUILT_IN_ROLES = [
    # (name, description, is_system, requires_mfa)
    ("super_admin", "Full system access — bypasses all permission checks.", 1, 1),
    ("admin", "System administration — manage users, groups, settings.", 1, 1),
    ("trader", "Full trading access — bots, positions, orders.", 1, 0),
    ("viewer", "Read-only access to all trading data.", 1, 0),
]

PERMISSIONS = [
    ("bots:read", "View bots"),
    ("bots:write", "Create and edit bots"),
    ("bots:delete", "Delete bots"),
    ("positions:read", "View positions"),
    ("positions:write", "Manage positions"),
    ("orders:read", "View orders"),
    ("orders:write", "Place orders"),
    ("accounts:read", "View accounts"),
    ("accounts:write", "Manage accounts"),
    ("reports:read", "View reports"),
    ("reports:write", "Create reports"),
    ("reports:delete", "Delete reports"),
    ("templates:read", "View templates"),
    ("templates:write", "Create and edit templates"),
    ("templates:delete", "Delete templates"),
    ("settings:read", "View settings"),
    ("settings:write", "Modify settings"),
    ("blacklist:read", "View blacklist"),
    ("blacklist:write", "Manage blacklist"),
    ("news:read", "View news"),
    ("news:write", "Manage news sources"),
    ("system:monitor", "View system status"),
    ("system:restart", "Restart services"),
    ("system:shutdown", "Shutdown services"),
    ("admin:users", "Manage users"),
    ("admin:groups", "Manage groups"),
    ("admin:roles", "Manage roles"),
    ("admin:permissions", "View permissions"),
    ("games:play", "Play games"),
]

# Role -> permission assignments
ROLE_PERMISSION_MAP = {
    # super_admin gets all permissions implicitly (is_superuser bypass),
    # but we still assign them for completeness
    "super_admin": [p[0] for p in PERMISSIONS],
    "admin": [
        "admin:users", "admin:groups", "admin:roles", "admin:permissions",
        "settings:read", "settings:write",
        "system:monitor", "system:restart", "system:shutdown",
        "blacklist:read", "blacklist:write",
        "news:read", "news:write",
    ],
    "trader": [
        "bots:read", "bots:write", "bots:delete",
        "positions:read", "positions:write",
        "orders:read", "orders:write",
        "accounts:read", "accounts:write",
        "reports:read", "reports:write",
        "templates:read", "templates:write", "templates:delete",
        "blacklist:read",
        "news:read",
        "games:play",
    ],
    "viewer": [
        "bots:read",
        "positions:read",
        "orders:read",
        "accounts:read",
        "reports:read",
        "news:read",
    ],
}

# Group -> role assignments
GROUP_ROLE_MAP = {
    "System Owners": ["super_admin"],
    "Administrators": ["admin"],
    "Traders": ["trader"],
    "Observers": ["viewer"],
}


def migrate():
    """Run RBAC migration."""
    logger.info("Starting RBAC migration...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Create tables
        logger.info("Creating RBAC tables...")
        cursor.execute(GROUPS_TABLE)
        cursor.execute(ROLES_TABLE)
        cursor.execute(PERMISSIONS_TABLE)
        cursor.execute(USER_GROUPS_TABLE)
        cursor.execute(GROUP_ROLES_TABLE)
        cursor.execute(ROLE_PERMISSIONS_TABLE)
        logger.info("  Tables created")

        # 2. Seed groups
        logger.info("Seeding built-in groups...")
        for name, description, is_system in BUILT_IN_GROUPS:
            cursor.execute(
                "INSERT OR IGNORE INTO groups (name, description, is_system) VALUES (?, ?, ?)",
                (name, description, is_system),
            )

        # 3. Seed roles
        logger.info("Seeding built-in roles...")
        for name, description, is_system, requires_mfa in BUILT_IN_ROLES:
            cursor.execute(
                "INSERT OR IGNORE INTO roles (name, description, is_system, requires_mfa) VALUES (?, ?, ?, ?)",
                (name, description, is_system, requires_mfa),
            )

        # 4. Seed permissions
        logger.info("Seeding permissions...")
        for name, description in PERMISSIONS:
            cursor.execute(
                "INSERT OR IGNORE INTO permissions (name, description) VALUES (?, ?)",
                (name, description),
            )

        conn.commit()

        # 5. Assign permissions to roles
        logger.info("Assigning permissions to roles...")
        for role_name, perm_names in ROLE_PERMISSION_MAP.items():
            cursor.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
            role_row = cursor.fetchone()
            if not role_row:
                continue
            role_id = role_row[0]

            for perm_name in perm_names:
                cursor.execute("SELECT id FROM permissions WHERE name = ?", (perm_name,))
                perm_row = cursor.fetchone()
                if not perm_row:
                    continue
                perm_id = perm_row[0]
                cursor.execute(
                    "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                    (role_id, perm_id),
                )

        # 6. Assign roles to groups
        logger.info("Assigning roles to groups...")
        for group_name, role_names in GROUP_ROLE_MAP.items():
            cursor.execute("SELECT id FROM groups WHERE name = ?", (group_name,))
            group_row = cursor.fetchone()
            if not group_row:
                continue
            group_id = group_row[0]

            for role_name in role_names:
                cursor.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
                role_row = cursor.fetchone()
                if not role_row:
                    continue
                role_id = role_row[0]
                cursor.execute(
                    "INSERT OR IGNORE INTO group_roles (group_id, role_id) VALUES (?, ?)",
                    (group_id, role_id),
                )

        # 7. Migrate existing users by is_superuser flag
        logger.info("Migrating existing users to RBAC groups...")

        # Get group IDs
        cursor.execute("SELECT id FROM groups WHERE name = 'System Owners'")
        system_owners_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM groups WHERE name = 'Traders'")
        traders_id = cursor.fetchone()[0]

        # Superusers -> System Owners
        cursor.execute("SELECT id FROM users WHERE is_superuser = 1")
        for (user_id,) in cursor.fetchall():
            cursor.execute(
                "INSERT OR IGNORE INTO user_groups (user_id, group_id) VALUES (?, ?)",
                (user_id, system_owners_id),
            )
            logger.info(f"  User {user_id} -> System Owners")

        # Regular users -> Traders
        cursor.execute("SELECT id FROM users WHERE is_superuser = 0")
        for (user_id,) in cursor.fetchall():
            cursor.execute(
                "INSERT OR IGNORE INTO user_groups (user_id, group_id) VALUES (?, ?)",
                (user_id, traders_id),
            )
            logger.info(f"  User {user_id} -> Traders")

        conn.commit()
        logger.info("RBAC migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"RBAC migration failed: {e}")
        raise

    finally:
        conn.close()


def rollback():
    """Rollback migration (informational only)."""
    logger.info(
        "Rollback: DROP TABLE role_permissions, group_roles, user_groups, "
        "permissions, roles, groups"
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
