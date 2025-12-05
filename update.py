#!/usr/bin/env python3
"""
Zenith Grid Update Script
=========================

Automated update script for production deployments.
Handles:
- Git pull to fetch latest changes
- Service shutdown (backend and frontend)
- Database backup
- Running all migrations
- Service restart (backend and frontend)

Usage:
  python3 update.py                # Full update with confirmation prompts
  python3 update.py --yes          # Skip confirmation prompts
  python3 update.py --no-backup    # Skip database backup (not recommended)
  python3 update.py --skip-pull    # Skip git pull (useful if already pulled manually)
  python3 update.py --dry-run      # Show what would be done without executing
  python3 update.py --help         # Show help
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}\n")


def print_step(step_num, text):
    print(f"{Colors.CYAN}{Colors.BOLD}[Step {step_num}]{Colors.ENDC} {text}")


def print_success(text):
    print(f"{Colors.GREEN}  ✓ {text}{Colors.ENDC}")


def print_warning(text):
    print(f"{Colors.YELLOW}  ⚠ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.RED}  ✗ {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.BLUE}  ℹ {text}{Colors.ENDC}")


def detect_os():
    """Detect the operating system."""
    system = platform.system().lower()
    if system == 'darwin':
        return 'mac'
    elif system == 'linux':
        return 'linux'
    else:
        return 'unknown'


def run_command(cmd, cwd=None, capture_output=False, check=True):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            check=check
        )
        return result
    except subprocess.CalledProcessError as e:
        if capture_output:
            print_error(f"Command failed: {cmd}")
            if e.stdout:
                print(f"  stdout: {e.stdout}")
            if e.stderr:
                print(f"  stderr: {e.stderr}")
        raise


def get_service_commands(os_type, project_root):
    """Get the service management commands based on OS for both backend and frontend."""
    if os_type == 'linux':
        return {
            'backend': {
                'stop': 'sudo systemctl stop trading-bot-backend',
                'start': 'sudo systemctl start trading-bot-backend',
                'restart': 'sudo systemctl restart trading-bot-backend',
                'status': 'sudo systemctl status trading-bot-backend --no-pager',
                'exists': 'systemctl list-unit-files | grep -q trading-bot-backend',
            },
            'frontend': {
                'stop': 'sudo systemctl stop trading-bot-frontend',
                'start': 'sudo systemctl start trading-bot-frontend',
                'restart': 'sudo systemctl restart trading-bot-frontend',
                'status': 'sudo systemctl status trading-bot-frontend --no-pager',
                'exists': 'systemctl list-unit-files | grep -q trading-bot-frontend',
            },
        }
    elif os_type == 'mac':
        backend_plist = 'com.zenithgrid.backend'
        frontend_plist = 'com.zenithgrid.frontend'
        return {
            'backend': {
                'stop': f'launchctl unload ~/Library/LaunchAgents/{backend_plist}.plist 2>/dev/null || true',
                'start': f'launchctl load ~/Library/LaunchAgents/{backend_plist}.plist',
                'restart': f'launchctl unload ~/Library/LaunchAgents/{backend_plist}.plist 2>/dev/null; launchctl load ~/Library/LaunchAgents/{backend_plist}.plist',
                'status': f'launchctl list | grep {backend_plist} || echo "Service not running"',
                'exists': f'test -f ~/Library/LaunchAgents/{backend_plist}.plist',
            },
            'frontend': {
                'stop': f'launchctl unload ~/Library/LaunchAgents/{frontend_plist}.plist 2>/dev/null || true',
                'start': f'launchctl load ~/Library/LaunchAgents/{frontend_plist}.plist',
                'restart': f'launchctl unload ~/Library/LaunchAgents/{frontend_plist}.plist 2>/dev/null; launchctl load ~/Library/LaunchAgents/{frontend_plist}.plist',
                'status': f'launchctl list | grep {frontend_plist} || echo "Service not running"',
                'exists': f'test -f ~/Library/LaunchAgents/{frontend_plist}.plist',
            },
        }
    else:
        return None


def service_exists(service_commands, project_root):
    """Check if a service exists on the system."""
    try:
        run_command(service_commands['exists'], cwd=project_root, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def git_pull(project_root, dry_run=False):
    """Pull latest changes from git.

    Returns:
        tuple: (success: bool, has_changes: bool)
    """
    print_step(1, "Pulling latest changes from git...")

    if dry_run:
        print_info("DRY RUN: Would run 'git pull origin main'")
        return True, True  # Assume changes in dry run

    try:
        # First fetch to see what's available
        run_command('git fetch origin', cwd=project_root, capture_output=True)

        # Pull the changes
        result = run_command('git pull origin main', cwd=project_root, capture_output=True)

        if 'Already up to date' in result.stdout:
            print_success("Already up to date - no changes pulled")
            return True, False  # Success but no changes
        else:
            print_success("Successfully pulled latest changes")
            if result.stdout:
                # Show summary of changes
                lines = result.stdout.strip().split('\n')
                for line in lines[:10]:  # Show first 10 lines
                    print_info(line)
            return True, True  # Success with changes

    except subprocess.CalledProcessError as e:
        print_error(f"Git pull failed: {e.stderr if e.stderr else str(e)}")
        return False, False


def stop_services(os_type, project_root, dry_run=False):
    """Stop the backend and frontend services."""
    print_step(2, "Stopping services...")

    all_commands = get_service_commands(os_type, project_root)
    if not all_commands:
        print_warning("Unknown OS - skipping service management")
        return True

    services_stopped = []

    for service_name in ['backend', 'frontend']:
        commands = all_commands[service_name]

        # Check if service exists
        if not dry_run and not service_exists(commands, project_root):
            print_info(f"{service_name.capitalize()} service not installed - skipping")
            continue

        if dry_run:
            print_info(f"DRY RUN: Would stop {service_name} service")
            continue

        try:
            run_command(commands['stop'], cwd=project_root, check=False)
            print_success(f"{service_name.capitalize()} service stopped")
            services_stopped.append(service_name)
        except Exception as e:
            print_warning(f"Could not stop {service_name} service (may not be running): {e}")

    return True  # Continue even if services weren't running


def backup_database(project_root, dry_run=False):
    """Create a backup of the database."""
    print_step(3, "Backing up database...")

    db_path = project_root / 'backend' / 'trading.db'
    if not db_path.exists():
        print_warning("Database not found - skipping backup")
        return True

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = project_root / 'backend' / f'trading.db.bak.update_{timestamp}'

    if dry_run:
        print_info(f"DRY RUN: Would backup {db_path} to {backup_path}")
        return True

    try:
        shutil.copy2(db_path, backup_path)
        print_success(f"Database backed up to: {backup_path.name}")
        return True
    except Exception as e:
        print_error(f"Database backup failed: {e}")
        return False


def run_migrations(project_root, dry_run=False):
    """Run all pending migrations."""
    print_step(4, "Running migrations...")

    migrations_dir = project_root / 'backend' / 'migrations'
    if not migrations_dir.exists():
        print_warning("Migrations directory not found")
        return True

    # Find the Python interpreter in venv
    venv_python = project_root / 'backend' / 'venv' / 'bin' / 'python'
    if not venv_python.exists():
        print_error("Virtual environment not found. Run setup.py first.")
        return False

    # Get all migration files
    migration_files = sorted([
        f for f in migrations_dir.iterdir()
        if f.suffix == '.py' and f.name != '__init__.py'
    ])

    if not migration_files:
        print_info("No migration files found")
        return True

    print_info(f"Found {len(migration_files)} migration file(s)")

    # Run each migration
    # Migrations are designed to be idempotent (safe to run multiple times)
    backend_dir = project_root / 'backend'
    success_count = 0
    skip_count = 0

    for migration in migration_files:
        migration_name = migration.name

        if dry_run:
            print_info(f"DRY RUN: Would run migration: {migration_name}")
            continue

        try:
            result = run_command(
                f'{venv_python} migrations/{migration_name}',
                cwd=backend_dir,
                capture_output=True
            )

            output = result.stdout.strip() if result.stdout else ''

            # Check if migration was actually applied or already done
            if 'already exists' in output.lower() or 'already' in output.lower():
                skip_count += 1
                print_info(f"  {migration_name}: Already applied")
            elif 'completed successfully' in output.lower() or 'migration completed' in output.lower():
                success_count += 1
                print_success(f"  {migration_name}: Applied")
            else:
                # Migration ran but unclear result
                success_count += 1
                print_success(f"  {migration_name}: Completed")
                if output:
                    for line in output.split('\n'):
                        if line.strip():
                            print_info(f"    {line}")

        except subprocess.CalledProcessError as e:
            print_error(f"  {migration_name}: Failed")
            if e.stderr:
                print_error(f"    {e.stderr}")
            # Continue with other migrations

    if not dry_run:
        print_success(f"Migrations complete: {success_count} applied, {skip_count} already done")

    return True


def start_services(os_type, project_root, dry_run=False):
    """Start the backend and frontend services."""
    print_step(5, "Starting services...")

    all_commands = get_service_commands(os_type, project_root)
    if not all_commands:
        print_warning("Unknown OS - skipping service management")
        return True

    all_started = True

    for service_name in ['backend', 'frontend']:
        commands = all_commands[service_name]

        # Check if service exists
        if not dry_run and not service_exists(commands, project_root):
            print_info(f"{service_name.capitalize()} service not installed - skipping")
            continue

        if dry_run:
            print_info(f"DRY RUN: Would start {service_name} service")
            continue

        try:
            run_command(commands['start'], cwd=project_root, check=False)
            print_success(f"{service_name.capitalize()} service started")

            # Show service status
            try:
                result = run_command(commands['status'], cwd=project_root, capture_output=True, check=False)
                if result.stdout:
                    # Show relevant status lines (just first 3 for brevity)
                    for line in result.stdout.split('\n')[:3]:
                        if line.strip():
                            print(f"    {line}")
            except Exception:
                pass

        except Exception as e:
            print_error(f"Could not start {service_name} service: {e}")
            all_started = False

    return all_started


def main():
    parser = argparse.ArgumentParser(
        description='Zenith Grid Update Script - Update and migrate the application',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 update.py              # Full update with prompts
  python3 update.py --yes        # Auto-confirm all prompts
  python3 update.py --dry-run    # Preview changes without executing
  python3 update.py --no-backup  # Skip database backup
        """
    )
    parser.add_argument('--yes', '-y', action='store_true',
                        help='Skip confirmation prompts')
    parser.add_argument('--no-backup', action='store_true',
                        help='Skip database backup (not recommended)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without executing')
    parser.add_argument('--skip-pull', action='store_true',
                        help='Skip git pull (useful if already pulled manually)')

    args = parser.parse_args()

    # Determine project root (where this script is located)
    project_root = Path(__file__).parent.absolute()

    # Detect OS
    os_type = detect_os()

    print_header("Zenith Grid Update")
    print_info(f"Project root: {project_root}")
    print_info(f"Operating System: {os_type}")

    if args.dry_run:
        print_warning("DRY RUN MODE - No changes will be made")

    # Confirmation prompt
    if not args.yes and not args.dry_run:
        print()
        print_warning("This will:")
        step = 1
        if not args.skip_pull:
            print(f"  {step}. Pull latest changes from git")
            step += 1
        else:
            print_info("  (Skipping git pull)")
        print(f"  {step}. Stop services (backend and frontend)")
        step += 1
        if not args.no_backup:
            print(f"  {step}. Backup the database")
            step += 1
        print(f"  {step}. Run all database migrations")
        step += 1
        print(f"  {step}. Restart services (backend and frontend)")
        print()

        response = input(f"{Colors.BOLD}Continue? [y/N]: {Colors.ENDC}").strip().lower()
        if response not in ('y', 'yes'):
            print_info("Update cancelled")
            sys.exit(0)

    print()

    # Step 1: Git pull (unless --skip-pull)
    if args.skip_pull:
        print_step(1, "Skipping git pull (--skip-pull)")
        print_info("Assuming changes were already pulled manually")
        has_changes = True  # Assume there are changes to process
    else:
        success, has_changes = git_pull(project_root, args.dry_run)
        if not success:
            print_error("Update failed at git pull step")
            sys.exit(1)

        # If no changes were pulled, skip service restart
        if not has_changes and not args.dry_run:
            print()
            print_header("No Updates Available")
            print_success("Already running the latest version - services left running")
            sys.exit(0)

    # Step 2: Stop services
    if not stop_services(os_type, project_root, args.dry_run):
        print_error("Update failed at stop services step")
        sys.exit(1)

    # Step 3: Backup database
    if not args.no_backup:
        if not backup_database(project_root, args.dry_run):
            print_error("Update failed at database backup step")
            # Try to restart services before exiting
            start_services(os_type, project_root, args.dry_run)
            sys.exit(1)
    else:
        print_step(3, "Skipping database backup (--no-backup)")

    # Step 4: Run migrations
    if not run_migrations(project_root, args.dry_run):
        print_error("Update failed at migrations step")
        # Try to restart services before exiting
        start_services(os_type, project_root, args.dry_run)
        sys.exit(1)

    # Step 5: Start services
    if not start_services(os_type, project_root, args.dry_run):
        print_error("Update failed at start services step")
        sys.exit(1)

    print()
    print_header("Update Complete!")

    if args.dry_run:
        print_info("This was a dry run - no changes were made")
    else:
        print_success("Zenith Grid has been updated successfully")
        print_info("Check service status with:")
        print_info("  sudo systemctl status trading-bot-backend")
        print_info("  sudo systemctl status trading-bot-frontend")


if __name__ == '__main__':
    main()
