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
  python3 update.py --preview      # Preview incoming changes (commits) before pulling
  python3 update.py --preview -d   # Preview with file diffs
  python3 update.py --changelog    # Show changelog for last 5 versions
  python3 update.py --changelog 10 # Show changelog for last 10 versions
  python3 update.py --changelog v0.86.0  # Show what changed in v0.86.0
  python3 update.py --help         # Show help
"""

import argparse
import os
import platform
import re
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


def get_sorted_tags(project_root):
    """Get all version tags sorted in proper semantic version order."""
    result = run_command('git tag', cwd=project_root, capture_output=True)
    if not result.stdout:
        return []

    tags = [t.strip() for t in result.stdout.strip().split('\n') if t.strip().startswith('v')]

    # Sort using semantic versioning (split by . and compare numerically)
    def version_key(tag):
        # Remove 'v' prefix and split by '.'
        version = tag.lstrip('v')
        parts = []
        for part in version.split('.'):
            # Handle parts with non-numeric suffixes like '1-beta'
            match = re.match(r'^(\d+)', part)
            if match:
                parts.append(int(match.group(1)))
            else:
                parts.append(0)
        return parts

    return sorted(tags, key=version_key)


def get_current_version(project_root):
    """Get the current installed version (most recent tag on HEAD or description).

    Returns:
        tuple: (version_string, is_exact_tag)
               is_exact_tag is True if HEAD is exactly at a tag
    """
    # Try to get exact tag at HEAD
    result = run_command(
        'git describe --tags --exact-match HEAD 2>/dev/null',
        cwd=project_root,
        capture_output=True,
        check=False
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip(), True

    # Get describe (tag + commits since)
    result = run_command(
        'git describe --tags --always 2>/dev/null',
        cwd=project_root,
        capture_output=True,
        check=False
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip(), False

    return "unknown", False


def show_changelog(project_root, changelog_arg):
    """Show changelog between version tags.

    Args:
        project_root: Path to project root
        changelog_arg: Either a number (show last N versions), a version string (show that version),
                      or None (default to last 5 versions)
    """
    print_header("Changelog")

    # Fetch from remote to get latest tags
    print_info("Fetching latest from remote...")
    run_command('git fetch origin --tags', cwd=project_root, capture_output=True, check=False)

    # Get latest version from remote
    try:
        latest_tag_result = run_command(
            'git tag --sort=-v:refname | head -1',
            cwd=project_root,
            capture_output=True,
            check=False
        )
        latest_version = latest_tag_result.stdout.strip() if latest_tag_result.stdout else "unknown"
    except Exception:
        latest_version = "unknown"

    # Show installed version
    current_version, is_exact = get_current_version(project_root)

    print(f"Latest: {Colors.CYAN}{Colors.BOLD}{latest_version}{Colors.ENDC}")
    if is_exact:
        print(f"Installed: {Colors.GREEN}{Colors.BOLD}{current_version}{Colors.ENDC}")
    else:
        print(f"Installed: {Colors.GREEN}{Colors.BOLD}{current_version}{Colors.ENDC} {Colors.YELLOW}(uncommitted changes){Colors.ENDC}")

    # Check if updates available and show brief message
    try:
        result = run_command(
            'git log --oneline HEAD..origin/main',
            cwd=project_root,
            capture_output=True,
            check=False
        )
        unpulled_commits = result.stdout.strip() if result.stdout else ''

        if unpulled_commits:
            commit_count = len(unpulled_commits.split('\n'))
            print()
            print(f"{Colors.YELLOW}📦 {commit_count} update(s) available - run 'python3 update.py' to apply{Colors.ENDC}")
    except Exception:
        pass  # Ignore errors checking for unpulled changes

    tags = get_sorted_tags(project_root)
    if len(tags) < 2:
        print_error("Not enough tags to show changelog (need at least 2)")
        return

    # Determine what to show based on argument
    if changelog_arg is None or changelog_arg == '':
        # Default: show last 5 versions
        num_versions = 5
        tags_to_show = tags[-num_versions:] if len(tags) >= num_versions else tags
    elif changelog_arg.isdigit():
        # Show last N versions
        num_versions = int(changelog_arg)
        tags_to_show = tags[-num_versions:] if len(tags) >= num_versions else tags
    elif changelog_arg.startswith('v'):
        # Show specific version
        if changelog_arg not in tags:
            print_error(f"Tag '{changelog_arg}' not found")
            print_info(f"Available tags: {', '.join(tags[-10:])}")
            return
        # Find this tag and the previous one
        tag_idx = tags.index(changelog_arg)
        if tag_idx == 0:
            print_warning(f"{changelog_arg} is the first tag - no previous version to compare")
            return
        tags_to_show = [tags[tag_idx - 1], changelog_arg]
    else:
        print_error(f"Invalid changelog argument: {changelog_arg}")
        print_info("Use a number (e.g., 10) or a version (e.g., v0.86.0)")
        return

    print(f"{Colors.HEADER}{Colors.BOLD}Version History:{Colors.ENDC}")
    print()

    # Show commits between consecutive tags (newest first)
    for i in range(len(tags_to_show) - 1, 0, -1):
        prev_tag = tags_to_show[i - 1]
        curr_tag = tags_to_show[i]

        # Get commits between these tags
        result = run_command(
            f'git log --format="%s" {prev_tag}..{curr_tag}',
            cwd=project_root,
            capture_output=True,
            check=False
        )

        # Get tag date
        date_result = run_command(
            f'git log -1 --format="%ai" {curr_tag}',
            cwd=project_root,
            capture_output=True,
            check=False
        )
        tag_date = date_result.stdout.strip()[:10] if date_result.stdout else ''

        # Mark installed version in the list
        is_installed = (curr_tag == current_version)
        marker = f" {Colors.GREEN}← installed{Colors.ENDC}" if is_installed else ""

        print(f"{Colors.CYAN}{Colors.BOLD}{curr_tag}{Colors.ENDC}", end='')
        if tag_date:
            print(f" {Colors.BLUE}({tag_date}){Colors.ENDC}{marker}")
        else:
            print(f"{marker}")

        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    print(f"  {Colors.YELLOW}•{Colors.ENDC} {line.strip()}")
        else:
            print(f"  {Colors.BLUE}(no commits){Colors.ENDC}")
        print()


def preview_incoming_changes(project_root, show_diff=False):
    """Preview commits and optionally diffs before pulling.

    Returns:
        bool: True if there are incoming changes, False if already up to date
    """
    print_header("Preview Incoming Changes")

    try:
        # Fetch latest from remote without merging
        print_info("Fetching from remote...")
        run_command('git fetch origin', cwd=project_root, capture_output=True)

        # Get current HEAD and remote HEAD
        current = run_command('git rev-parse HEAD', cwd=project_root, capture_output=True)
        current_hash = current.stdout.strip()

        remote = run_command('git rev-parse origin/main', cwd=project_root, capture_output=True)
        remote_hash = remote.stdout.strip()

        if current_hash == remote_hash:
            print_success("Already up to date - no new commits")
            return False

        # Show commit log
        print()
        print(f"{Colors.CYAN}{Colors.BOLD}Commits since last pull:{Colors.ENDC}")
        print()

        result = run_command(
            'git log --oneline HEAD..origin/main',
            cwd=project_root,
            capture_output=True
        )

        if result.stdout:
            commit_count = len(result.stdout.strip().split('\n'))
            for line in result.stdout.strip().split('\n'):
                print(f"  {Colors.YELLOW}•{Colors.ENDC} {line}")
            print()
            print_info(f"Total: {commit_count} commit(s)")

        # Show file summary
        print()
        print(f"{Colors.CYAN}{Colors.BOLD}Files changed:{Colors.ENDC}")
        print()

        result = run_command(
            'git diff --stat HEAD..origin/main',
            cwd=project_root,
            capture_output=True
        )

        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                print(f"  {line}")

        # Optionally show full diff
        if show_diff:
            print()
            print(f"{Colors.CYAN}{Colors.BOLD}Full diff:{Colors.ENDC}")
            print()

            result = run_command(
                'git diff HEAD..origin/main',
                cwd=project_root,
                capture_output=True
            )

            if result.stdout:
                for line in result.stdout.split('\n'):
                    # Colorize diff output
                    if line.startswith('+') and not line.startswith('+++'):
                        print(f"{Colors.GREEN}{line}{Colors.ENDC}")
                    elif line.startswith('-') and not line.startswith('---'):
                        print(f"{Colors.RED}{line}{Colors.ENDC}")
                    elif line.startswith('@@'):
                        print(f"{Colors.CYAN}{line}{Colors.ENDC}")
                    elif line.startswith('diff '):
                        print(f"\n{Colors.BOLD}{line}{Colors.ENDC}")
                    else:
                        print(line)

        print()
        return True

    except subprocess.CalledProcessError as e:
        print_error(f"Failed to preview changes: {e.stderr if e.stderr else str(e)}")
        return False


def determine_services_to_restart(changed_files):
    """Determine which services need restart based on changed files.

    Args:
        changed_files: List of file paths that changed

    Returns:
        set: Set of service names that need restart ('backend', 'frontend')
    """
    services = set()

    # Root-level files that don't require restarts
    no_restart_files = {
        'update.py', 'setup.py', 'README.md', 'CLAUDE.md', 'LICENSE',
        '.gitignore', '.pre-commit-config.yaml', 'COMMERCIALIZATION.md',
    }

    for filepath in changed_files:
        # Normalize path separators
        filepath = filepath.replace('\\', '/')

        # Skip files that don't require restarts
        if filepath in no_restart_files:
            continue

        # Skip documentation and config files
        if filepath.endswith('.md') and not filepath.startswith('backend/'):
            continue

        # Backend files - Python code in backend/, requirements, migrations
        if (filepath.startswith('backend/') or
            filepath.startswith('migrations/') or
            'requirements' in filepath.lower()):
            services.add('backend')

        # Frontend files - React/TypeScript code, package.json, etc.
        if (filepath.startswith('frontend/') or
            'package.json' in filepath or
            'package-lock.json' in filepath or
            'vite.config' in filepath or
            'tailwind.config' in filepath or
            'tsconfig' in filepath):
            services.add('frontend')

        # .env files affect both services
        if '.env' in filepath and not filepath.endswith('.md'):
            services.add('backend')
            services.add('frontend')

        # Scripts in scripts/ folder don't need restarts
        if filepath.startswith('scripts/'):
            continue

        # Deployment configs don't need service restart (they're for deploying)
        if filepath.startswith('deployment/'):
            continue

    return services


def git_pull(project_root, dry_run=False):
    """Pull latest changes from git.

    Returns:
        tuple: (success: bool, has_changes: bool, services_to_restart: set)
    """
    print_step(1, "Pulling latest changes from git...")

    if dry_run:
        print_info("DRY RUN: Would run 'git pull origin main'")
        return True, True, {'backend', 'frontend'}  # Assume both in dry run

    try:
        # First fetch to see what's available
        run_command('git fetch origin', cwd=project_root, capture_output=True)

        # Get the commit range before pulling
        current_head = run_command('git rev-parse HEAD', cwd=project_root, capture_output=True)
        current_hash = current_head.stdout.strip()

        # Pull the changes
        result = run_command('git pull origin main', cwd=project_root, capture_output=True)

        if 'Already up to date' in result.stdout:
            print_success("Already up to date - no changes pulled")
            return True, False, set()  # Success but no changes, no services to restart
        else:
            print_success("Successfully pulled latest changes")
            if result.stdout:
                # Show summary of changes
                lines = result.stdout.strip().split('\n')
                for line in lines[:10]:  # Show first 10 lines
                    print_info(line)

            # Get list of changed files since previous HEAD
            diff_result = run_command(
                f'git diff --name-only {current_hash}..HEAD',
                cwd=project_root,
                capture_output=True
            )
            changed_files = [f.strip() for f in diff_result.stdout.strip().split('\n') if f.strip()]

            # Determine which services need restart
            services = determine_services_to_restart(changed_files)

            if services:
                print_info(f"Services requiring restart: {', '.join(sorted(services))}")
            else:
                print_info("No service restarts required (config/docs only)")

            return True, True, services

    except subprocess.CalledProcessError as e:
        print_error(f"Git pull failed: {e.stderr if e.stderr else str(e)}")
        return False, False, set()


def stop_services(os_type, project_root, dry_run=False, services_to_stop=None):
    """Stop the backend and/or frontend services.

    Args:
        os_type: Operating system type ('linux', 'mac', 'unknown')
        project_root: Path to project root
        dry_run: If True, only show what would be done
        services_to_stop: Set of services to stop ('backend', 'frontend').
                         If None, stops all services.
    """
    if services_to_stop is None:
        services_to_stop = {'backend', 'frontend'}

    if not services_to_stop:
        print_step(2, "No services require restart - skipping stop")
        return True

    print_step(2, f"Stopping services: {', '.join(sorted(services_to_stop))}...")

    all_commands = get_service_commands(os_type, project_root)
    if not all_commands:
        print_warning("Unknown OS - skipping service management")
        return True

    services_stopped = []

    for service_name in ['backend', 'frontend']:
        if service_name not in services_to_stop:
            continue

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


def start_services(os_type, project_root, dry_run=False, services_to_start=None):
    """Start the backend and/or frontend services.

    Args:
        os_type: Operating system type ('linux', 'mac', 'unknown')
        project_root: Path to project root
        dry_run: If True, only show what would be done
        services_to_start: Set of services to start ('backend', 'frontend').
                          If None, starts all services.
    """
    if services_to_start is None:
        services_to_start = {'backend', 'frontend'}

    if not services_to_start:
        print_step(5, "No services require restart - skipping start")
        return True

    print_step(5, f"Starting services: {', '.join(sorted(services_to_start))}...")

    all_commands = get_service_commands(os_type, project_root)
    if not all_commands:
        print_warning("Unknown OS - skipping service management")
        return True

    all_started = True

    for service_name in ['backend', 'frontend']:
        if service_name not in services_to_start:
            continue

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
  python3 update.py                  # Full update with prompts
  python3 update.py --yes            # Auto-confirm all prompts
  python3 update.py --dry-run        # Preview changes without executing
  python3 update.py --no-backup      # Skip database backup
  python3 update.py --changelog      # Show last 5 versions' changes
  python3 update.py --changelog 10   # Show last 10 versions' changes
  python3 update.py --changelog v0.86.0  # Show what changed in v0.86.0
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
    parser.add_argument('--preview', '-p', action='store_true',
                        help='Preview incoming commits before pulling (then exit)')
    parser.add_argument('--diff', '-d', action='store_true',
                        help='With --preview, also show full file diffs')
    parser.add_argument('--changelog', '-c', nargs='?', const='5', default=None,
                        metavar='N|VERSION',
                        help='Show changelog: N versions (default 5) or specific version (e.g., v0.86.0)')

    args = parser.parse_args()

    # Determine project root (where this script is located)
    project_root = Path(__file__).parent.absolute()

    # Detect OS
    os_type = detect_os()

    # Handle --changelog mode (exit after showing changelog)
    if args.changelog is not None:
        show_changelog(project_root, args.changelog)
        sys.exit(0)

    # Handle --preview mode (exit after showing preview)
    if args.preview:
        has_changes = preview_incoming_changes(project_root, show_diff=args.diff)
        if has_changes:
            print_info("Run 'python3 update.py' to apply these changes")
        sys.exit(0)

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
    services_to_restart = {'backend', 'frontend'}  # Default to both
    if args.skip_pull:
        print_step(1, "Skipping git pull (--skip-pull)")
        print_info("Assuming changes were already pulled manually - will restart all services")
        has_changes = True  # Assume there are changes to process
    else:
        success, has_changes, services_to_restart = git_pull(project_root, args.dry_run)
        if not success:
            print_error("Update failed at git pull step")
            sys.exit(1)

        # If no changes were pulled, skip service restart
        if not has_changes and not args.dry_run:
            print()
            print_header("No Updates Available")
            print_success("Already running the latest version - services left running")
            sys.exit(0)

    # Step 2: Stop services (only those that need restart)
    if not stop_services(os_type, project_root, args.dry_run, services_to_restart):
        print_error("Update failed at stop services step")
        sys.exit(1)

    # Step 3: Backup database (only if backend is being restarted)
    if 'backend' in services_to_restart:
        if not args.no_backup:
            if not backup_database(project_root, args.dry_run):
                print_error("Update failed at database backup step")
                # Try to restart services before exiting
                start_services(os_type, project_root, args.dry_run, services_to_restart)
                sys.exit(1)
        else:
            print_step(3, "Skipping database backup (--no-backup)")
    else:
        print_step(3, "Skipping database backup (no backend changes)")

    # Step 4: Run migrations (only if backend is being restarted)
    if 'backend' in services_to_restart:
        if not run_migrations(project_root, args.dry_run):
            print_error("Update failed at migrations step")
            # Try to restart services before exiting
            start_services(os_type, project_root, args.dry_run, services_to_restart)
            sys.exit(1)
    else:
        print_step(4, "Skipping migrations (no backend changes)")

    # Step 5: Start services (only those that need restart)
    if not start_services(os_type, project_root, args.dry_run, services_to_restart):
        print_error("Update failed at start services step")
        sys.exit(1)

    print()
    print_header("Update Complete!")

    if args.dry_run:
        print_info("This was a dry run - no changes were made")
    else:
        if services_to_restart:
            print_success(f"Restarted services: {', '.join(sorted(services_to_restart))}")
        else:
            print_success("No services required restart (config/docs only changes)")
        print_info("Check service status with:")
        if 'backend' in services_to_restart:
            print_info("  sudo systemctl status trading-bot-backend")
        if 'frontend' in services_to_restart:
            print_info("  sudo systemctl status trading-bot-frontend")


if __name__ == '__main__':
    main()
