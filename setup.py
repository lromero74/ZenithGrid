#!/usr/bin/env python3
"""
Zenith Grid Setup Wizard
========================

Interactive setup script for initial application configuration.
Handles:
- OS detection (Linux/Mac)
- Python venv creation and dependency installation
- Frontend npm dependency installation
- Database initialization and migrations
- .env configuration with API keys
- Initial admin user creation
- Optional service installation (systemd/launchd)
- Auto-start services and display access URL

Usage:
  python3 setup.py                      # Full setup wizard
  python3 setup.py --services-only      # Only create/install service files
  python3 setup.py --uninstall-services # Stop and remove service files
  python3 setup.py --cleanup            # Remove dependencies (venv, node_modules, optionally db)
  python3 setup.py --help               # Show help
"""

import argparse
import getpass
import itertools
import os
import platform
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# Required Python packages (mapped to import names where different)
REQUIRED_PACKAGES = {
    'fastapi': 'fastapi',
    'uvicorn': 'uvicorn',
    'websockets': 'websockets',
    'sqlalchemy': 'sqlalchemy',
    'aiosqlite': 'aiosqlite',
    'greenlet': 'greenlet',
    'pydantic': 'pydantic',
    'pydantic-settings': 'pydantic_settings',
    'email-validator': 'email_validator',
    'python-dotenv': 'dotenv',
    'httpx': 'httpx',
    'pandas': 'pandas',
    'numpy': 'numpy',
    'ta': 'ta',
    'python-jose': 'jose',
    'passlib': 'passlib',
    'bcrypt': 'bcrypt',
    'coinbase-advanced-py': 'coinbase',
    'anthropic': 'anthropic',
    'google-generativeai': 'google.generativeai',
    'openai': 'openai',
    'web3': 'web3',
    'eth-account': 'eth_account',
    'aiohttp': 'aiohttp',
    'feedparser': 'feedparser',
    'trafilatura': 'trafilatura',
}

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
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.ENDC}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.ENDC}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ {text}{Colors.ENDC}")


class Spinner:
    """Animated spinner for long-running operations"""

    def __init__(self, message="Working"):
        self.message = message
        self.running = False
        self.thread = None
        self.spinner_chars = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])

    def _spin(self):
        while self.running:
            char = next(self.spinner_chars)
            sys.stdout.write(f"\r{Colors.CYAN}{char} {self.message}...{Colors.ENDC}")
            sys.stdout.flush()
            time.sleep(0.1)

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.start()

    def stop(self, success=True, message=None):
        self.running = False
        if self.thread:
            self.thread.join()
        # Clear the spinner line
        sys.stdout.write('\r' + ' ' * (len(self.message) + 10) + '\r')
        sys.stdout.flush()
        # Print final status
        if message:
            if success:
                print_success(message)
            else:
                print_error(message)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop(success=(exc_type is None))
        return False


def run_with_spinner(command, message, success_msg=None, error_msg=None, **kwargs):
    """Run a subprocess command with a spinner animation"""
    spinner = Spinner(message)
    spinner.start()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            **kwargs
        )
        spinner.stop(
            success=(result.returncode == 0),
            message=success_msg if result.returncode == 0 else (error_msg or f"Failed: {result.stderr[:100]}")
        )
        return result
    except Exception as e:
        spinner.stop(success=False, message=error_msg or str(e))
        raise


def reexec_with_python311():
    """Re-execute this script with Python 3.11"""
    python311_path = shutil.which('python3.11')
    if python311_path:
        print()
        print_info("Restarting setup with Python 3.11...")
        print()
        # Re-exec with new Python, preserving any arguments
        os.execv(python311_path, [python311_path, __file__] + sys.argv[1:])
    else:
        print_error("Could not find python3.11 in PATH after installation")
        print_info("Please re-run setup manually with: python3.11 setup.py")


def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.resolve()

def detect_os():
    """Detect operating system"""
    system = platform.system().lower()
    if system == 'darwin':
        return 'mac'
    elif system == 'linux':
        return 'linux'
    else:
        return 'unknown'

def prompt_yes_no(question, default='yes'):
    """Ask a yes/no question"""
    valid = {'yes': True, 'y': True, 'no': False, 'n': False}
    if default == 'yes':
        prompt = '[Y/n]'
    else:
        prompt = '[y/N]'

    while True:
        choice = input(f"{question} {prompt}: ").strip().lower()
        if choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            print("Please respond with 'yes' or 'no' (or 'y' or 'n').")

def prompt_input(question, default=None, required=True, password=False):
    """Prompt for user input"""
    if default:
        prompt = f"{question} [{default}]: "
    else:
        prompt = f"{question}: "

    while True:
        if password:
            value = getpass.getpass(prompt)
        else:
            value = input(prompt).strip()

        if not value and default:
            return default
        elif not value and required:
            print("This field is required.")
        else:
            return value

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password meets requirements"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    return True, ""


# AI Provider configuration with API key URLs
AI_PROVIDERS = {
    '1': {
        'name': 'Claude (Anthropic)',
        'key': 'claude',
        'env_key': 'anthropic_api_key',
        'url': 'https://console.anthropic.com/settings/keys',
    },
    '2': {
        'name': 'ChatGPT (OpenAI)',
        'key': 'openai',
        'env_key': 'openai_api_key',
        'url': 'https://platform.openai.com/api-keys',
    },
    '3': {
        'name': 'Gemini (Google)',
        'key': 'gemini',
        'env_key': 'gemini_api_key',
        'url': 'https://aistudio.google.com/apikey',
    },
    '4': {
        'name': 'Grok (xAI)',
        'key': 'grok',
        'env_key': 'grok_api_key',
        'url': 'https://console.x.ai/',
    },
}


def prompt_for_ai_provider(config):
    """Prompt user to select an AI provider and enter their API key"""
    print()
    print_header("Select AI Provider")
    print()

    for num, provider in AI_PROVIDERS.items():
        print(f"  {num}. {provider['name']}")
    print()

    while True:
        choice = input("Enter choice (1-4): ").strip()
        if choice in AI_PROVIDERS:
            break
        print_warning("Please enter 1, 2, 3, or 4")

    provider = AI_PROVIDERS[choice]
    print()
    print_info(f"Selected: {provider['name']}")
    print_info(f"Get your API key at: {provider['url']}")
    print()

    api_key = prompt_input(f"{provider['name']} API key", required=False)

    if api_key:
        config['system_ai_provider'] = provider['key']
        config[provider['env_key']] = api_key
        print_success(f"Configured {provider['name']} as system AI provider")
    else:
        print_warning("No API key provided, skipping AI configuration")

    return config


def check_python_version():
    """Ensure Python 3.10+ is being used (required for numpy 2.x, pandas 2.x)"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print_error(f"Python 3.10+ required. You have Python {version.major}.{version.minor}")

        os_type = detect_os()

        # Check if Python 3.11 is already installed
        python311_path = shutil.which('python3.11')
        if python311_path:
            print_info(f"Python 3.11 found at: {python311_path}")
            reexec_with_python311()
            return False  # Only reached if reexec fails

        # Offer to install Python 3.11
        if os_type == 'mac':
            # Check if brew is available
            if shutil.which('brew'):
                print()
                if prompt_yes_no("Install Python 3.11 via Homebrew?", default='yes'):
                    try:
                        result = run_with_spinner(
                            ['brew', 'install', 'python@3.11'],
                            "Installing Python 3.11 (this may take a few minutes)",
                            success_msg="Python 3.11 installed!",
                            error_msg="Failed to install Python 3.11"
                        )
                        if result.returncode == 0:
                            reexec_with_python311()
                    except Exception as e:
                        print_error(f"Failed to install Python 3.11: {e}")
            else:
                # Homebrew not installed - offer to install it
                print_warning("Homebrew is not installed (required for Python 3.11 on Mac)")
                print()
                if prompt_yes_no("Install Homebrew?", default='yes'):
                    try:
                        result = run_with_spinner(
                            ['/bin/bash', '-c',
                             'NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'],
                            "Installing Homebrew (this may take a few minutes)",
                            success_msg="Homebrew installed!",
                            error_msg="Failed to install Homebrew"
                        )
                        if result.returncode == 0:
                            print()
                            # Now install Python 3.11
                            result = run_with_spinner(
                                ['/opt/homebrew/bin/brew', 'install', 'python@3.11'],
                                "Installing Python 3.11 (this may take a few minutes)",
                                success_msg="Python 3.11 installed!",
                                error_msg="Failed to install Python 3.11"
                            )
                            if result.returncode == 0:
                                reexec_with_python311()
                    except Exception as e:
                        print_error(f"Installation failed: {e}")
                        print_info("Try manually: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
                        print_info("Then: brew install python@3.11 && python3.11 setup.py")
                else:
                    print_info("To install manually:")
                    print_info("  1. /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
                    print_info("  2. brew install python@3.11")
                    print_info("  3. python3.11 setup.py")

        elif os_type == 'linux':
            # Detect package manager
            if shutil.which('dnf'):
                print()
                if prompt_yes_no("Install Python 3.11 via dnf?", default='yes'):
                    try:
                        result = run_with_spinner(
                            ['sudo', 'dnf', 'install', '-y', 'python3.11'],
                            "Installing Python 3.11",
                            success_msg="Python 3.11 installed!",
                            error_msg="Failed to install Python 3.11"
                        )
                        if result.returncode == 0:
                            reexec_with_python311()
                    except Exception as e:
                        print_error(f"Failed to install Python 3.11: {e}")
            elif shutil.which('apt'):
                print()
                if prompt_yes_no("Install Python 3.11 via apt?", default='yes'):
                    try:
                        run_with_spinner(
                            ['sudo', 'apt', 'update'],
                            "Updating package lists",
                            success_msg="Package lists updated"
                        )
                        result = run_with_spinner(
                            ['sudo', 'apt', 'install', '-y', 'python3.11', 'python3.11-venv'],
                            "Installing Python 3.11",
                            success_msg="Python 3.11 installed!",
                            error_msg="Failed to install Python 3.11"
                        )
                        if result.returncode == 0:
                            reexec_with_python311()
                    except Exception as e:
                        print_error(f"Failed to install Python 3.11: {e}")
            else:
                print_info("Please install Python 3.11 manually, then run: python3.11 setup.py")

        return False

    print_success(f"Python {version.major}.{version.minor} detected")
    return True

def check_venv_exists(project_root):
    """Check if virtual environment exists"""
    venv_path = project_root / 'backend' / 'venv'
    return venv_path.exists()

def create_venv(project_root):
    """Create Python virtual environment"""
    venv_path = project_root / 'backend' / 'venv'
    print_info("Creating Python virtual environment...")

    try:
        subprocess.run([sys.executable, '-m', 'venv', str(venv_path)], check=True)
        print_success("Virtual environment created")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create virtual environment: {e}")
        return False

def get_venv_python(project_root):
    """Get the path to venv Python"""
    os_type = detect_os()
    if os_type == 'linux' or os_type == 'mac':
        return project_root / 'backend' / 'venv' / 'bin' / 'python'
    else:
        return project_root / 'backend' / 'venv' / 'Scripts' / 'python.exe'

def get_venv_pip(project_root):
    """Get the path to venv pip"""
    os_type = detect_os()
    if os_type == 'linux' or os_type == 'mac':
        return project_root / 'backend' / 'venv' / 'bin' / 'pip'
    else:
        return project_root / 'backend' / 'venv' / 'Scripts' / 'pip.exe'

def check_package_installed(pip_path, package_name, import_name):
    """Check if a Python package is installed in the venv"""
    try:
        # Use pip show to check if package is installed
        result = subprocess.run(
            [str(pip_path), 'show', package_name],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False

def get_missing_packages(project_root):
    """Get list of missing Python packages"""
    pip_path = get_venv_pip(project_root)
    missing = []

    for package_name, import_name in REQUIRED_PACKAGES.items():
        if not check_package_installed(pip_path, package_name, import_name):
            missing.append(package_name)

    return missing

def install_dependencies(project_root, force_reinstall=False):
    """Install Python dependencies"""
    pip_path = get_venv_pip(project_root)
    requirements_path = project_root / 'backend' / 'requirements.txt'

    # First check what's missing
    missing = get_missing_packages(project_root)

    if not missing and not force_reinstall:
        print_success("All Python dependencies already installed")
        return True

    if missing:
        print_info(f"Missing packages: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}")

    print_info("Installing Python dependencies from requirements.txt...")

    try:
        # Upgrade pip first
        subprocess.run([str(pip_path), 'install', '--upgrade', 'pip'],
                      capture_output=True, check=False)

        # Install all requirements
        result = subprocess.run(
            [str(pip_path), 'install', '-r', str(requirements_path)],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print_warning("Some packages may have failed to install")
            print_info(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        else:
            print_success("Dependencies installed successfully")

        # Verify critical packages
        critical = ['fastapi', 'uvicorn', 'sqlalchemy', 'bcrypt', 'pydantic']
        still_missing = []
        for pkg in critical:
            if not check_package_installed(pip_path, pkg, REQUIRED_PACKAGES.get(pkg, pkg)):
                still_missing.append(pkg)

        if still_missing:
            print_warning(f"Critical packages still missing: {', '.join(still_missing)}")
            return False

        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install dependencies: {e}")
        return False

def install_single_package(project_root, package_name):
    """Install a single Python package"""
    pip_path = get_venv_pip(project_root)
    try:
        subprocess.run([str(pip_path), 'install', package_name],
                      capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def check_npm_installed():
    """Check if npm is installed"""
    try:
        subprocess.run(['npm', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def check_node_modules_exists(project_root):
    """Check if frontend node_modules exists and has packages"""
    node_modules = project_root / 'frontend' / 'node_modules'
    if not node_modules.exists():
        return False
    # Check if it has some content (not empty)
    try:
        contents = list(node_modules.iterdir())
        return len(contents) > 10  # Should have many packages
    except Exception:
        return False

def install_frontend_dependencies(project_root, force_reinstall=False):
    """Install frontend dependencies"""
    frontend_path = project_root / 'frontend'

    # Check if already installed
    if check_node_modules_exists(project_root) and not force_reinstall:
        print_success("Frontend dependencies already installed")
        return True

    print_info("Installing frontend dependencies...")

    try:
        result = subprocess.run(
            ['npm', 'install'],
            cwd=str(frontend_path),
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print_warning("npm install had issues")
            print_info(result.stderr[-300:] if len(result.stderr) > 300 else result.stderr)
        else:
            print_success("Frontend dependencies installed")

        return check_node_modules_exists(project_root)
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install frontend dependencies: {e}")
        return False
    except FileNotFoundError:
        print_error("npm not found. Please install Node.js first.")
        return False

def initialize_database(project_root):
    """Initialize the SQLite database with all required tables"""
    db_path = project_root / 'backend' / 'trading.db'

    print_info("Initializing database...")

    # Create all tables from models
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                hashed_password TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                is_superuser INTEGER DEFAULT 0,
                display_name TEXT,
                last_seen_history_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login_at DATETIME
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)")

        # Accounts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                exchange TEXT,
                api_key_name TEXT,
                api_private_key TEXT,
                chain_id INTEGER,
                wallet_address TEXT,
                wallet_private_key TEXT,
                rpc_url TEXT,
                wallet_type TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_used_at DATETIME
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_accounts_user_id ON accounts(user_id)")

        # Bots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                name TEXT UNIQUE,
                description TEXT,
                account_id INTEGER REFERENCES accounts(id),
                exchange_type TEXT DEFAULT 'cex',
                chain_id INTEGER,
                dex_router TEXT,
                wallet_private_key TEXT,
                rpc_url TEXT,
                wallet_address TEXT,
                strategy_type TEXT,
                strategy_config TEXT,
                product_id TEXT DEFAULT 'ETH-BTC',
                product_ids TEXT DEFAULT '[]',
                split_budget_across_pairs INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                check_interval_seconds INTEGER DEFAULT 300,
                reserved_btc_balance REAL DEFAULT 0.0,
                reserved_usd_balance REAL DEFAULT 0.0,
                budget_percentage REAL DEFAULT 0.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_signal_check DATETIME,
                last_ai_check DATETIME
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_bots_user_id ON bots(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_bots_strategy_type ON bots(strategy_type)")

        # Bot templates table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                name TEXT UNIQUE,
                description TEXT,
                strategy_type TEXT,
                strategy_config TEXT,
                product_ids TEXT DEFAULT '[]',
                split_budget_across_pairs INTEGER DEFAULT 0,
                is_default INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_bot_templates_user_id ON bot_templates(user_id)")

        # Positions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER REFERENCES bots(id),
                account_id INTEGER REFERENCES accounts(id),
                product_id TEXT DEFAULT 'ETH-BTC',
                status TEXT DEFAULT 'open',
                opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                closed_at DATETIME,
                exchange_type TEXT DEFAULT 'cex',
                chain_id INTEGER,
                dex_router TEXT,
                wallet_address TEXT,
                strategy_config_snapshot TEXT,
                initial_quote_balance REAL,
                max_quote_allowed REAL,
                total_quote_spent REAL DEFAULT 0.0,
                total_base_acquired REAL DEFAULT 0.0,
                average_buy_price REAL DEFAULT 0.0,
                sell_price REAL,
                total_quote_received REAL,
                profit_quote REAL,
                profit_percentage REAL,
                btc_usd_price_at_open REAL,
                btc_usd_price_at_close REAL,
                profit_usd REAL,
                highest_price_since_tp REAL,
                trailing_tp_active INTEGER DEFAULT 0,
                highest_price_since_entry REAL,
                last_error_message TEXT,
                last_error_timestamp DATETIME,
                notes TEXT,
                closing_via_limit INTEGER DEFAULT 0,
                limit_close_order_id TEXT,
                trailing_stop_loss_price REAL,
                trailing_stop_loss_active INTEGER DEFAULT 0,
                entry_stop_loss REAL,
                entry_take_profit_target REAL,
                pattern_data TEXT,
                exit_reason TEXT
            )
        """)

        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER REFERENCES positions(id),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                side TEXT,
                quote_amount REAL,
                base_amount REAL,
                price REAL,
                trade_type TEXT,
                order_id TEXT,
                macd_value REAL,
                macd_signal REAL,
                macd_histogram REAL
            )
        """)

        # Signals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER REFERENCES positions(id),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                signal_type TEXT,
                macd_value REAL,
                macd_signal REAL,
                macd_histogram REAL,
                price REAL,
                action_taken TEXT,
                reason TEXT
            )
        """)

        # Settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                value TEXT,
                value_type TEXT,
                description TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_settings_key ON settings(key)")

        # Market data table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                price REAL,
                macd_value REAL,
                macd_signal REAL,
                macd_histogram REAL,
                volume REAL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_market_data_timestamp ON market_data(timestamp)")

        # AI bot logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_bot_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER REFERENCES bots(id),
                position_id INTEGER REFERENCES positions(id),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                thinking TEXT,
                decision TEXT,
                confidence REAL,
                current_price REAL,
                position_status TEXT,
                product_id TEXT,
                context TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_ai_bot_logs_bot_id ON ai_bot_logs(bot_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_ai_bot_logs_timestamp ON ai_bot_logs(timestamp)")

        # Scanner logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scanner_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER REFERENCES bots(id),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                product_id TEXT NOT NULL,
                scan_type TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT,
                current_price REAL,
                volume_ratio REAL,
                pattern_data TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_scanner_logs_bot_id ON scanner_logs(bot_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_scanner_logs_timestamp ON scanner_logs(timestamp)")

        # Pending orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER NOT NULL REFERENCES positions(id),
                bot_id INTEGER NOT NULL REFERENCES bots(id),
                order_id TEXT NOT NULL UNIQUE,
                product_id TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                limit_price REAL NOT NULL,
                quote_amount REAL NOT NULL,
                base_amount REAL,
                trade_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                filled_at DATETIME,
                canceled_at DATETIME,
                filled_price REAL,
                filled_quote_amount REAL,
                filled_base_amount REAL,
                fills TEXT,
                remaining_base_amount REAL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_pending_orders_order_id ON pending_orders(order_id)")

        # Order history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                bot_id INTEGER NOT NULL REFERENCES bots(id),
                position_id INTEGER REFERENCES positions(id),
                product_id TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                trade_type TEXT NOT NULL,
                quote_amount REAL NOT NULL,
                base_amount REAL,
                price REAL,
                status TEXT NOT NULL,
                order_id TEXT,
                error_message TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_order_history_timestamp ON order_history(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_order_history_status ON order_history(status)")

        # Blacklisted coins table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blacklisted_coins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                symbol TEXT,
                reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_blacklisted_coins_user_id ON blacklisted_coins(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_blacklisted_coins_symbol ON blacklisted_coins(symbol)")

        conn.commit()
        print_success("Database tables created")
        return True

    except Exception as e:
        conn.rollback()
        print_error(f"Failed to initialize database: {e}")
        return False
    finally:
        conn.close()

def create_admin_user(project_root, email, password, display_name=None):
    """Create the initial admin user"""
    db_path = project_root / 'backend' / 'trading.db'

    # Get venv Python path
    venv_python = get_venv_python(project_root)

    # Hash password using bcrypt via venv Python (bcrypt is installed there)
    hash_script = f'''
import bcrypt
hashed = bcrypt.hashpw({repr(password.encode('utf-8'))}, bcrypt.gensalt())
print(hashed.decode('utf-8'))
'''
    result = subprocess.run(
        [str(venv_python), '-c', hash_script],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print_error(f"Failed to hash password: {result.stderr}")
        return False

    hashed = result.stdout.strip()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if user already exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (email.lower(),))
        existing = cursor.fetchone()

        if existing:
            print_warning(f"User {email} already exists")
            return True

        cursor.execute("""
            INSERT INTO users (email, hashed_password, is_active, is_superuser, display_name, created_at, updated_at)
            VALUES (?, ?, 1, 1, ?, ?, ?)
        """, (email.lower(), hashed, display_name, datetime.utcnow(), datetime.utcnow()))

        conn.commit()
        print_success(f"Admin user '{email}' created")
        return True

    except Exception as e:
        conn.rollback()
        print_error(f"Failed to create admin user: {e}")
        return False
    finally:
        conn.close()

def generate_env_file(project_root, config):
    """Generate the .env file with provided configuration"""
    env_path = project_root / 'backend' / '.env'

    # Generate a secure JWT secret key
    jwt_secret = secrets.token_urlsafe(32)

    env_content = f"""# Zenith Grid Configuration
# Generated by setup wizard on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# =============================================================================
# JWT Authentication (Required)
# =============================================================================
JWT_SECRET_KEY={jwt_secret}
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# =============================================================================
# Database Configuration
# =============================================================================
DATABASE_URL=sqlite+aiosqlite:///./trading.db

# =============================================================================
# CORS Origins (comma-separated)
# =============================================================================
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# =============================================================================
# System AI Configuration (for coin categorization)
# This AI analyzes coins to categorize them (APPROVED, BORDERLINE, BLACKLISTED).
# News and YouTube are pulled directly from RSS feeds, not AI.
# Per-user AI trading bot keys are stored in the database via Settings.
# =============================================================================
"""

    # Add system AI provider
    provider = config.get('system_ai_provider', 'claude')
    env_content += f"SYSTEM_AI_PROVIDER={provider}\n"

    if config.get('anthropic_api_key'):
        env_content += f"ANTHROPIC_API_KEY={config['anthropic_api_key']}\n"
    else:
        env_content += "# ANTHROPIC_API_KEY=\n"

    if config.get('openai_api_key'):
        env_content += f"OPENAI_API_KEY={config['openai_api_key']}\n"
    else:
        env_content += "# OPENAI_API_KEY=\n"

    if config.get('gemini_api_key'):
        env_content += f"GEMINI_API_KEY={config['gemini_api_key']}\n"
    else:
        env_content += "# GEMINI_API_KEY=\n"

    if config.get('grok_api_key'):
        env_content += f"GROK_API_KEY={config['grok_api_key']}\n"
    else:
        env_content += "# GROK_API_KEY=\n"

    env_content += """
# =============================================================================
# Coinbase API (Add your credentials in the app after setup)
# =============================================================================
# COINBASE_API_KEY=your_coinbase_api_key
# COINBASE_API_SECRET=your_coinbase_api_secret

# =============================================================================
# Application Settings
# =============================================================================
DEBUG=false
LOG_LEVEL=INFO
"""

    try:
        with open(env_path, 'w') as f:
            f.write(env_content)
        print_success(".env file created")
        return True
    except Exception as e:
        print_error(f"Failed to create .env file: {e}")
        return False

def create_systemd_service(project_root, user):
    """Create systemd service files for Linux"""
    services_dir = project_root / 'deployment'
    services_dir.mkdir(exist_ok=True)

    backend_service = f"""[Unit]
Description=Zenith Grid Trading Bot Backend
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={project_root}/backend
Environment="PATH={project_root}/backend/venv/bin"
ExecStart={project_root}/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""

    frontend_service = f"""[Unit]
Description=Zenith Grid Trading Bot Frontend
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={project_root}/frontend
ExecStart=/usr/bin/npm run dev -- --host 0.0.0.0
Restart=always
RestartSec=10
Environment=NODE_ENV=development

[Install]
WantedBy=multi-user.target
"""

    try:
        backend_path = services_dir / 'zenith-backend.service'
        frontend_path = services_dir / 'zenith-frontend.service'

        with open(backend_path, 'w') as f:
            f.write(backend_service)

        with open(frontend_path, 'w') as f:
            f.write(frontend_service)

        print_success("Systemd service files created in deployment/")
        print_info("To install services, run:")
        print(f"  sudo cp {backend_path} /etc/systemd/system/")
        print(f"  sudo cp {frontend_path} /etc/systemd/system/")
        print("  sudo systemctl daemon-reload")
        print("  sudo systemctl enable zenith-backend zenith-frontend")
        print("  sudo systemctl start zenith-backend zenith-frontend")
        return True

    except Exception as e:
        print_error(f"Failed to create systemd service files: {e}")
        return False

def create_launchd_plist(project_root, user):
    """Create launchd plist files for macOS"""
    plist_dir = project_root / 'deployment'
    plist_dir.mkdir(exist_ok=True)

    backend_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.zenithgrid.backend</string>
    <key>ProgramArguments</key>
    <array>
        <string>{project_root}/backend/venv/bin/uvicorn</string>
        <string>app.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8100</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{project_root}/backend</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/zenith-backend.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/zenith-backend.error.log</string>
</dict>
</plist>
"""

    frontend_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.zenithgrid.frontend</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/npm</string>
        <string>run</string>
        <string>dev</string>
        <string>--</string>
        <string>--host</string>
        <string>0.0.0.0</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{project_root}/frontend</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/zenith-frontend.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/zenith-frontend.error.log</string>
</dict>
</plist>
"""

    try:
        backend_path = plist_dir / 'com.zenithgrid.backend.plist'
        frontend_path = plist_dir / 'com.zenithgrid.frontend.plist'

        with open(backend_path, 'w') as f:
            f.write(backend_plist)

        with open(frontend_path, 'w') as f:
            f.write(frontend_plist)

        print_success("LaunchAgent plist files created in deployment/")
        print_info("To install services, run:")
        print(f"  cp {backend_path} ~/Library/LaunchAgents/")
        print(f"  cp {frontend_path} ~/Library/LaunchAgents/")
        print("  launchctl load ~/Library/LaunchAgents/com.zenithgrid.backend.plist")
        print("  launchctl load ~/Library/LaunchAgents/com.zenithgrid.frontend.plist")
        return True

    except Exception as e:
        print_error(f"Failed to create launchd plist files: {e}")
        return False

def start_services_manually(project_root):
    """Start backend and frontend services manually"""
    print_info("Starting services...")

    # Start backend
    backend_dir = project_root / 'backend'
    venv_python = get_venv_python(project_root)

    print_info("Starting backend server...")
    backend_proc = subprocess.Popen(
        [str(venv_python), '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8100'],
        cwd=str(backend_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # Start frontend
    frontend_dir = project_root / 'frontend'

    print_info("Starting frontend server...")
    frontend_proc = subprocess.Popen(
        ['npm', 'run', 'dev', '--', '--host', '0.0.0.0'],
        cwd=str(frontend_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # Wait a moment for services to start
    import time
    time.sleep(3)

    # Check if processes are running
    if backend_proc.poll() is None:
        print_success("Backend server started (PID: {})".format(backend_proc.pid))
    else:
        print_warning("Backend server may have failed to start")

    if frontend_proc.poll() is None:
        print_success("Frontend server started (PID: {})".format(frontend_proc.pid))
    else:
        print_warning("Frontend server may have failed to start")

    return True

def run_setup():
    """Main setup wizard"""
    print_header("Zenith Grid Setup Wizard")

    project_root = get_project_root()
    os_type = detect_os()
    current_user = os.getenv('USER', 'user')

    print(f"Project directory: {project_root}")
    print(f"Detected OS: {os_type.capitalize()}")
    print(f"Current user: {current_user}")
    print()

    # Check Python version
    if not check_python_version():
        return False

    # Step 1: Python Virtual Environment & Dependencies
    print_step(1, "Python Environment Setup")

    # Auto-create venv if it doesn't exist
    if not check_venv_exists(project_root):
        print_info("Virtual environment not found. Creating...")
        if not create_venv(project_root):
            print_error("Failed to create virtual environment. Exiting.")
            return False
    else:
        print_success("Virtual environment exists")

    # Check and install missing Python dependencies automatically
    missing_packages = get_missing_packages(project_root)
    if missing_packages:
        print_info(f"Found {len(missing_packages)} missing Python packages")
        if not install_dependencies(project_root):
            print_warning("Some dependencies failed to install")
            if not prompt_yes_no("Continue anyway?", default='no'):
                return False
    else:
        print_success("All Python dependencies installed")

    # Step 2: Frontend Dependencies
    print_step(2, "Frontend Dependencies")
    if check_npm_installed():
        # Auto-install if node_modules doesn't exist
        if not check_node_modules_exists(project_root):
            print_info("Frontend dependencies not found. Installing...")
            if not install_frontend_dependencies(project_root):
                print_warning("Frontend dependencies failed to install")
        else:
            print_success("Frontend dependencies already installed")
    else:
        print_warning("npm not found. Please install Node.js to run the frontend.")
        print_info("Download from: https://nodejs.org/")

    # Step 3: Database Initialization
    print_step(3, "Database Initialization")
    db_path = project_root / 'backend' / 'trading.db'

    if db_path.exists():
        print_warning(f"Database already exists at {db_path}")
        if prompt_yes_no("Reinitialize database? (This will NOT delete existing data)", default='no'):
            initialize_database(project_root)
    else:
        print_info("Creating new database...")
        if not initialize_database(project_root):
            return False

    # Step 4: Environment Configuration
    print_step(4, "Environment Configuration")
    env_path = project_root / 'backend' / '.env'

    config = {}

    if env_path.exists():
        print_warning(".env file already exists")
        if not prompt_yes_no("Regenerate .env file? (Will backup existing)", default='no'):
            print_info("Keeping existing .env file")
        else:
            # Backup existing
            backup_path = env_path.with_suffix('.env.backup')
            shutil.copy(env_path, backup_path)
            print_success(f"Backed up existing .env to {backup_path}")

            print()
            print_info("System AI (optional) - used for coin categorization.")
            print_info("This AI analyzes coins weekly to categorize them as APPROVED,")
            print_info("BORDERLINE, QUESTIONABLE, or BLACKLISTED.")
            print_info("(News and YouTube are pulled directly from RSS feeds, not AI)")
            print_info("(Per-user AI trading bot keys are configured in Settings)")
            print()

            if prompt_yes_no("Configure a system AI provider for coin categorization?", default='no'):
                config = prompt_for_ai_provider(config)

            generate_env_file(project_root, config)
    else:
        print()
        print_info("System AI (optional) - used for coin categorization.")
        print_info("This AI analyzes coins weekly to categorize them as APPROVED,")
        print_info("BORDERLINE, QUESTIONABLE, or BLACKLISTED.")
        print_info("(News and YouTube are pulled directly from RSS feeds, not AI)")
        print_info("(Per-user AI trading bot keys are configured in Settings)")
        print()

        if prompt_yes_no("Configure a system AI provider for coin categorization?", default='no'):
            config = prompt_for_ai_provider(config)

        generate_env_file(project_root, config)

    # Step 5: Create Admin User
    print_step(5, "Create Admin User")

    # Check if any users exist
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    conn.close()

    create_user = False
    if user_count > 0:
        print_info(f"{user_count} user(s) already exist in database")
        if prompt_yes_no("Create another admin user?", default='no'):
            create_user = True
        else:
            print_info("Skipping user creation")
    else:
        print_info("No users found. Creating initial admin user...")
        create_user = True

    if create_user:
        print()
        while True:
            email = prompt_input("Admin email address")
            if validate_email(email):
                break
            print_error("Invalid email format. Please try again.")

        while True:
            password = prompt_input("Admin password (min 8 characters)", password=True)
            valid, msg = validate_password(password)
            if not valid:
                print_error(msg)
                continue

            confirm = prompt_input("Confirm password", password=True)
            if password == confirm:
                break
            print_error("Passwords do not match. Please try again.")

        display_name = prompt_input("Display name (optional)", required=False)

        # Need to ensure bcrypt is available
        sys.path.insert(0, str(project_root / 'backend'))
        create_admin_user(project_root, email, password, display_name or None)

    # Step 6: Service Installation
    print_step(6, "Service Installation (Optional)")

    if os_type == 'linux':
        print_info("Linux detected - can create systemd service files")
        if prompt_yes_no("Create systemd service files for auto-start?", default='no'):
            service_user = prompt_input("User to run services as", default=current_user)
            create_systemd_service(project_root, service_user)
    elif os_type == 'mac':
        print_info("macOS detected - can create launchd plist files")
        if prompt_yes_no("Create launchd plist files for auto-start?", default='no'):
            create_launchd_plist(project_root, current_user)
    else:
        print_warning("Unknown OS - skipping service installation")

    # Step 7: Start Services
    print_step(7, "Start Services")

    if prompt_yes_no("Start services now?"):
        start_services_manually(project_root)

        print()
        print_header("Setup Complete!")
        print()
        print(f"{Colors.GREEN}{Colors.BOLD}Zenith Grid is now running!{Colors.ENDC}")
        print()
        print("Access the application at:")
        print(f"  {Colors.CYAN}http://localhost:5173{Colors.ENDC}")
        print()
        print("Backend API is available at:")
        print(f"  {Colors.CYAN}http://localhost:8100{Colors.ENDC}")
        print()
        print("To stop services, press Ctrl+C or kill the processes.")
        print()

        # Keep script running to maintain child processes
        print_info("Press Enter to exit setup (services will continue running in background)...")
        input()
    else:
        print()
        print_header("Setup Complete!")
        print()
        print("To start the application manually:")
        print()
        print("  Backend:")
        print(f"    cd {project_root}/backend")
        print("    ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100")
        print()
        print("  Frontend:")
        print(f"    cd {project_root}/frontend")
        print("    npm run dev -- --host 0.0.0.0")
        print()
        print("Then access the application at:")
        print(f"  {Colors.CYAN}http://localhost:5173{Colors.ENDC}")

    return True


def run_services_only():
    """Create and optionally install service files only (skip full setup)"""
    print_header("Zenith Grid Service Installation")

    project_root = get_project_root()
    os_type = detect_os()
    current_user = os.getenv('USER', 'user')

    print(f"Project directory: {project_root}")
    print(f"Detected OS: {os_type.capitalize()}")
    print(f"Current user: {current_user}")
    print()

    if os_type == 'linux':
        print_info("Linux detected - creating systemd service files")
        service_user = prompt_input("User to run services as", default=current_user)
        if not create_systemd_service(project_root, service_user):
            return False

        print()
        if prompt_yes_no("Install services now (requires sudo)?"):
            services_dir = project_root / 'deployment'
            backend_path = services_dir / 'zenith-backend.service'
            frontend_path = services_dir / 'zenith-frontend.service'

            print_info("Installing systemd services...")
            try:
                subprocess.run(['sudo', 'cp', str(backend_path), '/etc/systemd/system/'], check=True)
                subprocess.run(['sudo', 'cp', str(frontend_path), '/etc/systemd/system/'], check=True)
                subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
                print_success("Service files installed")

                if prompt_yes_no("Enable services to start on boot?"):
                    subprocess.run(['sudo', 'systemctl', 'enable', 'zenith-backend', 'zenith-frontend'], check=True)
                    print_success("Services enabled")

                if prompt_yes_no("Start services now?"):
                    subprocess.run(['sudo', 'systemctl', 'start', 'zenith-backend', 'zenith-frontend'], check=True)
                    print_success("Services started")
                    print()
                    print(f"Access the application at: {Colors.CYAN}http://localhost:5173{Colors.ENDC}")

            except subprocess.CalledProcessError as e:
                print_error(f"Failed to install services: {e}")
                return False

    elif os_type == 'mac':
        print_info("macOS detected - creating launchd plist files")
        if not create_launchd_plist(project_root, current_user):
            return False

        print()
        if prompt_yes_no("Install LaunchAgents now?"):
            plist_dir = project_root / 'deployment'
            backend_plist = plist_dir / 'com.zenithgrid.backend.plist'
            frontend_plist = plist_dir / 'com.zenithgrid.frontend.plist'
            launch_agents_dir = Path.home() / 'Library' / 'LaunchAgents'

            print_info("Installing LaunchAgents...")
            try:
                # Ensure LaunchAgents directory exists
                launch_agents_dir.mkdir(parents=True, exist_ok=True)

                # Copy plist files
                shutil.copy(backend_plist, launch_agents_dir / 'com.zenithgrid.backend.plist')
                shutil.copy(frontend_plist, launch_agents_dir / 'com.zenithgrid.frontend.plist')
                print_success("Plist files copied to ~/Library/LaunchAgents/")

                if prompt_yes_no("Load services now (start on boot)?"):
                    # Unload first if already loaded (ignore errors)
                    subprocess.run(['launchctl', 'unload', str(launch_agents_dir / 'com.zenithgrid.backend.plist')],
                                  capture_output=True)
                    subprocess.run(['launchctl', 'unload', str(launch_agents_dir / 'com.zenithgrid.frontend.plist')],
                                  capture_output=True)

                    # Load services
                    subprocess.run(['launchctl', 'load', str(launch_agents_dir / 'com.zenithgrid.backend.plist')], check=True)
                    subprocess.run(['launchctl', 'load', str(launch_agents_dir / 'com.zenithgrid.frontend.plist')], check=True)
                    print_success("Services loaded and will start on boot")
                    print()
                    print_info("Services are starting... wait a few seconds then access:")
                    print(f"  {Colors.CYAN}http://localhost:5173{Colors.ENDC}")
                    print()
                    print("To check service status:")
                    print("  launchctl list | grep zenithgrid")
                    print()
                    print("To view logs:")
                    print("  tail -f /tmp/zenith-backend.log")
                    print("  tail -f /tmp/zenith-frontend.log")

            except Exception as e:
                print_error(f"Failed to install services: {e}")
                return False
    else:
        print_error("Unknown OS - cannot create service files")
        return False

    print()
    print_header("Service Installation Complete!")
    return True


def run_uninstall_services():
    """Stop and remove service files"""
    print_header("Zenith Grid Service Removal")

    project_root = get_project_root()
    os_type = detect_os()

    print(f"Project directory: {project_root}")
    print(f"Detected OS: {os_type.capitalize()}")
    print()

    if os_type == 'linux':
        print_info("Removing systemd services...")

        backend_service = Path('/etc/systemd/system/zenith-backend.service')
        frontend_service = Path('/etc/systemd/system/zenith-frontend.service')

        # Check if services exist
        backend_exists = backend_service.exists()
        frontend_exists = frontend_service.exists()

        if not backend_exists and not frontend_exists:
            print_warning("No Zenith Grid services found installed")
            return True

        try:
            # Stop services first
            print_info("Stopping services...")
            subprocess.run(['sudo', 'systemctl', 'stop', 'zenith-backend'], capture_output=True)
            subprocess.run(['sudo', 'systemctl', 'stop', 'zenith-frontend'], capture_output=True)
            print_success("Services stopped")

            # Disable services
            print_info("Disabling services...")
            subprocess.run(['sudo', 'systemctl', 'disable', 'zenith-backend'], capture_output=True)
            subprocess.run(['sudo', 'systemctl', 'disable', 'zenith-frontend'], capture_output=True)
            print_success("Services disabled")

            # Remove service files
            print_info("Removing service files...")
            if backend_exists:
                subprocess.run(['sudo', 'rm', str(backend_service)], check=True)
                print_success(f"Removed {backend_service}")
            if frontend_exists:
                subprocess.run(['sudo', 'rm', str(frontend_service)], check=True)
                print_success(f"Removed {frontend_service}")

            # Reload systemd
            subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
            print_success("Systemd reloaded")

        except subprocess.CalledProcessError as e:
            print_error(f"Failed to remove services: {e}")
            return False

    elif os_type == 'mac':
        print_info("Removing launchd services...")

        launch_agents_dir = Path.home() / 'Library' / 'LaunchAgents'
        backend_plist = launch_agents_dir / 'com.zenithgrid.backend.plist'
        frontend_plist = launch_agents_dir / 'com.zenithgrid.frontend.plist'

        # Check if services exist
        backend_exists = backend_plist.exists()
        frontend_exists = frontend_plist.exists()

        if not backend_exists and not frontend_exists:
            print_warning("No Zenith Grid services found installed")
            return True

        try:
            # Unload services first (stop them)
            print_info("Unloading services...")
            if backend_exists:
                subprocess.run(['launchctl', 'unload', str(backend_plist)], capture_output=True)
            if frontend_exists:
                subprocess.run(['launchctl', 'unload', str(frontend_plist)], capture_output=True)
            print_success("Services unloaded (stopped)")

            # Remove plist files
            print_info("Removing plist files...")
            if backend_exists:
                backend_plist.unlink()
                print_success(f"Removed {backend_plist}")
            if frontend_exists:
                frontend_plist.unlink()
                print_success(f"Removed {frontend_plist}")

        except Exception as e:
            print_error(f"Failed to remove services: {e}")
            return False

    else:
        print_error("Unknown OS - cannot remove services")
        return False

    # Also remove local deployment files if they exist
    deployment_dir = project_root / 'deployment'
    if deployment_dir.exists():
        if prompt_yes_no("Also remove local service files in deployment/?", default='no'):
            try:
                shutil.rmtree(deployment_dir)
                print_success("Removed deployment/ directory")
            except Exception as e:
                print_warning(f"Could not remove deployment/: {e}")

    print()
    print_header("Service Removal Complete!")
    print()
    print("Services have been stopped and removed.")
    print("To run Zenith Grid manually:")
    print()
    print("  Backend:")
    print(f"    cd {project_root}/backend")
    print("    ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100")
    print()
    print("  Frontend:")
    print(f"    cd {project_root}/frontend")
    print("    npm run dev -- --host 0.0.0.0")
    print()
    return True


def run_cleanup():
    """Remove dependencies and optionally database for fresh setup"""
    print_header("Zenith Grid Cleanup")

    project_root = get_project_root()

    print(f"Project directory: {project_root}")
    print()

    venv_path = project_root / 'backend' / 'venv'
    node_modules_path = project_root / 'frontend' / 'node_modules'
    db_path = project_root / 'backend' / 'trading.db'
    env_path = project_root / 'backend' / '.env'
    deployment_path = project_root / 'deployment'

    # Show what exists
    print_info("Current state:")
    print(f"  Python venv:      {'exists' if venv_path.exists() else 'not found'}")
    print(f"  node_modules:     {'exists' if node_modules_path.exists() else 'not found'}")
    print(f"  Database:         {'exists' if db_path.exists() else 'not found'}")
    print(f"  .env file:        {'exists' if env_path.exists() else 'not found'}")
    print(f"  deployment/:      {'exists' if deployment_path.exists() else 'not found'}")
    print()

    # Always remove venv and node_modules
    if venv_path.exists():
        print_info("Removing Python virtual environment...")
        try:
            shutil.rmtree(venv_path)
            print_success(f"Removed {venv_path}")
        except Exception as e:
            print_error(f"Failed to remove venv: {e}")

    if node_modules_path.exists():
        print_info("Removing node_modules...")
        try:
            shutil.rmtree(node_modules_path)
            print_success(f"Removed {node_modules_path}")
        except Exception as e:
            print_error(f"Failed to remove node_modules: {e}")

    # Ask about database
    if db_path.exists():
        print()
        print_warning("Database contains user accounts, bots, and trading history!")
        if prompt_yes_no("Delete database (trading.db)?", default='no'):
            try:
                db_path.unlink()
                print_success(f"Removed {db_path}")
            except Exception as e:
                print_error(f"Failed to remove database: {e}")

            # Also look for database backups
            backend_path = project_root / 'backend'
            backups = list(backend_path.glob('trading.db*backup*')) + list(backend_path.glob('*.db.bak'))
            if backups:
                print_info(f"Found {len(backups)} database backup(s)")
                if prompt_yes_no("Delete database backups too?", default='no'):
                    for backup in backups:
                        try:
                            backup.unlink()
                            print_success(f"Removed {backup.name}")
                        except Exception as e:
                            print_warning(f"Failed to remove {backup.name}: {e}")

    # Ask about .env
    if env_path.exists():
        print()
        print_warning(".env contains API keys and configuration!")
        if prompt_yes_no("Delete .env file?", default='no'):
            try:
                env_path.unlink()
                print_success(f"Removed {env_path}")
            except Exception as e:
                print_error(f"Failed to remove .env: {e}")

            # Check for .env backups
            env_backups = list((project_root / 'backend').glob('.env.backup*'))
            if env_backups:
                if prompt_yes_no("Delete .env backups too?", default='no'):
                    for backup in env_backups:
                        try:
                            backup.unlink()
                            print_success(f"Removed {backup.name}")
                        except Exception as e:
                            print_warning(f"Failed to remove {backup.name}: {e}")

    # Ask about deployment directory - but warn about git-tracked files
    if deployment_path.exists():
        # Check for generated (non-git-tracked) files like plist files
        generated_files = list(deployment_path.glob('*.plist'))
        git_tracked = ['auto-deploy.sh', 'deploy-from-git.sh', 'deploy.sh',
                       'manage-auto-deploy.sh', 'nginx-trading-bot.conf', 'trading-bot.service']

        if generated_files:
            print()
            print_info(f"Found {len(generated_files)} generated plist file(s) in deployment/")
            if prompt_yes_no("Delete generated service files (keeps git-tracked scripts)?", default='no'):
                for f in generated_files:
                    try:
                        f.unlink()
                        print_success(f"Removed {f.name}")
                    except Exception as e:
                        print_warning(f"Failed to remove {f.name}: {e}")
        else:
            print()
            print_warning("deployment/ contains git-tracked deployment scripts")
            print_info("  These are templates for Linux/EC2 production deployment")
            print_info("  Use 'git checkout deployment/' to restore if deleted")

    print()
    print_header("Cleanup Complete!")
    print()
    print("You can now run a fresh setup with:")
    print(f"  cd {project_root}")
    print("  python3 setup.py")
    print()
    return True


def main():
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(
        description='Zenith Grid Setup Wizard',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 setup.py                      Full interactive setup
  python3 setup.py --services-only      Create and install service files only
  python3 setup.py --uninstall-services Stop and remove installed services
  python3 setup.py --cleanup            Remove dependencies for fresh setup
        """
    )
    parser.add_argument(
        '--services-only',
        action='store_true',
        help='Only create/install service files (skip full setup)'
    )
    parser.add_argument(
        '--uninstall-services',
        action='store_true',
        help='Stop and remove installed service files'
    )
    parser.add_argument(
        '--cleanup',
        action='store_true',
        help='Remove venv, node_modules, and optionally db/.env for fresh setup'
    )

    args = parser.parse_args()

    if args.cleanup:
        return run_cleanup()
    elif args.uninstall_services:
        return run_uninstall_services()
    elif args.services_only:
        return run_services_only()
    else:
        return run_setup()


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)
