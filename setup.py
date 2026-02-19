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
    'Pillow': 'PIL',
    'pyotp': 'pyotp',
    'qrcode': 'qrcode',
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


def get_homebrew_prefix():
    """
    Get Homebrew installation prefix based on architecture.

    Returns:
        str: Homebrew prefix path (/opt/homebrew for Apple Silicon, /usr/local for Intel)
    """
    machine = platform.machine()

    if machine == 'arm64':
        # Apple Silicon (M1, M2, M3, etc.)
        return '/opt/homebrew'
    else:
        # Intel Mac
        return '/usr/local'


def get_brew_path():
    """
    Get full path to brew executable.

    Returns:
        str: Full path to brew, or None if not found
    """
    # First try to find in PATH
    brew_in_path = shutil.which('brew')
    if brew_in_path:
        return brew_in_path

    # Try architecture-specific paths
    prefix = get_homebrew_prefix()
    brew_path = f'{prefix}/bin/brew'

    if os.path.exists(brew_path):
        return brew_path

    return None


def check_xcode_tools():
    """
    Check if Xcode Command Line Tools are installed (required for Homebrew on macOS).

    Returns:
        bool: True if installed, False otherwise
    """
    try:
        result = subprocess.run(
            ['xcode-select', '-p'],
            capture_output=True,
            check=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def install_xcode_tools():
    """Prompt user to install Xcode Command Line Tools"""
    print_warning("Xcode Command Line Tools not found (required for Homebrew)")
    print()
    if prompt_yes_no("Install Xcode Command Line Tools?", default='yes'):
        print_info("Opening Xcode Command Line Tools installer...")
        print_info("After installation completes, please re-run: python3 setup.py")
        try:
            subprocess.run(['xcode-select', '--install'], check=False)
            sys.exit(0)
        except Exception as e:
            print_error(f"Failed to launch installer: {e}")
            return False
    else:
        print_info("Xcode Command Line Tools required for Homebrew.")
        print_info("Install manually: xcode-select --install")
        return False


def update_shell_path_for_homebrew():
    """
    Update PATH to include Homebrew after fresh installation.
    This allows subsequent commands to find brew without restarting shell.
    """
    prefix = get_homebrew_prefix()
    brew_bin = f'{prefix}/bin'

    # Add to current process PATH
    current_path = os.environ.get('PATH', '')
    if brew_bin not in current_path:
        os.environ['PATH'] = f'{brew_bin}:{current_path}'
        print_info(f"Added {brew_bin} to PATH for this session")


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


def display_license_and_get_acceptance(project_root):
    """Display the license file and require user to accept it before proceeding"""
    license_path = project_root / 'LICENSE'

    if not license_path.exists():
        print_error("LICENSE file not found in project root!")
        print_info("Cannot proceed without license file.")
        return False

    print_header("License Agreement")
    print()

    # Read and display the license
    try:
        with open(license_path, 'r') as f:
            license_text = f.read()
    except Exception as e:
        print_error(f"Failed to read LICENSE file: {e}")
        return False

    # Display the license with a border
    print(f"{Colors.CYAN}{'─' * 60}{Colors.ENDC}")
    print()
    for line in license_text.strip().split('\n'):
        print(f"  {line}")
    print()
    print(f"{Colors.CYAN}{'─' * 60}{Colors.ENDC}")
    print()

    print_warning("IMPORTANT: You must read and agree to the license above before using this software.")
    print()

    # Require explicit "I AGREE" instead of just yes/no
    while True:
        prompt_msg = (
            f"{Colors.BOLD}Type 'I AGREE' to accept the license "
            f"terms (or 'quit' to exit): {Colors.ENDC}"
        )
        response = input(prompt_msg).strip()
        if response.upper() == 'I AGREE':
            print()
            print_success("License accepted. Proceeding with setup...")
            return True
        elif response.lower() in ('quit', 'exit', 'q'):
            print()
            print_info("Setup cancelled. You must accept the license to use this software.")
            return False
        else:
            print_warning("Please type 'I AGREE' exactly to accept, or 'quit' to exit.")


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
        'name': 'Gemini (Google) - free tier available',
        'key': 'gemini',
        'env_key': 'gemini_api_key',
        'url': 'https://aistudio.google.com/apikey',
    },
    '2': {
        'name': 'Claude (Anthropic)',
        'key': 'claude',
        'env_key': 'anthropic_api_key',
        'url': 'https://console.anthropic.com/settings/keys',
    },
    '3': {
        'name': 'ChatGPT (OpenAI)',
        'key': 'openai',
        'env_key': 'openai_api_key',
        'url': 'https://platform.openai.com/api-keys',
    },
    '4': {
        'name': 'Grok (xAI)',
        'key': 'grok',
        'env_key': 'grok_api_key',
        'url': 'https://console.x.ai/',
    },
}


def prompt_for_ai_provider(config, existing_env=None):
    """Prompt user to select an AI provider and enter their API key

    Args:
        config: Configuration dict to update
        existing_env: Optional dict of existing .env values
    """
    if existing_env is None:
        existing_env = {}

    print()
    print_header("Select AI Provider")

    # Check if there's an existing provider configured
    existing_provider = existing_env.get('SYSTEM_AI_PROVIDER', '').lower()
    existing_provider_name = None
    default_choice = '1'

    if existing_provider:
        for num, provider in AI_PROVIDERS.items():
            if provider['key'] == existing_provider:
                existing_provider_name = provider['name']
                default_choice = num
                break

    if existing_provider_name:
        print_info(f"Currently configured: {existing_provider_name}")
    print()

    for num, provider in AI_PROVIDERS.items():
        marker = " (current)" if provider['key'] == existing_provider else ""
        print(f"  {num}. {provider['name']}{marker}")
    print()

    while True:
        choice = input(f"Enter choice [{default_choice}]: ").strip() or default_choice
        if choice in AI_PROVIDERS:
            break
        print_warning("Please enter 1, 2, 3, or 4")

    provider = AI_PROVIDERS[choice]
    print()
    print_info(f"Selected: {provider['name']}")
    print_info(f"Get your API key at: {provider['url']}")
    print()

    # Check for existing API key
    existing_key = existing_env.get(provider['env_key'], '')
    if existing_key:
        masked_key = existing_key[:8] + '...' + existing_key[-4:] if len(existing_key) > 12 else '***'
        print_info(f"Existing key found: {masked_key}")
        if prompt_yes_no("Keep existing API key?", default='yes'):
            api_key = existing_key
        else:
            api_key = prompt_input(f"New {provider['name']} API key", required=False)
    else:
        api_key = prompt_input(f"{provider['name']} API key", required=False)

    if api_key:
        config['system_ai_provider'] = provider['key']
        config[provider['env_key']] = api_key
        if existing_key and api_key == existing_key:
            print_success(f"Keeping existing {provider['name']} configuration")
        else:
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
            # Check for Xcode Command Line Tools first (required for Homebrew)
            if not check_xcode_tools():
                if not install_xcode_tools():
                    sys.exit(1)
                # If we get here, user declined - can't proceed
                sys.exit(1)

            # Check if brew is available
            brew_path = get_brew_path()
            if brew_path:
                print()
                if prompt_yes_no("Install Python 3.11 via Homebrew?", default='yes'):
                    try:
                        result = run_with_spinner(
                            [brew_path, 'install', 'python@3.11'],
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
                        # Run Homebrew installation script
                        brew_install_url = (
                            "https://raw.githubusercontent.com"
                            "/Homebrew/install/HEAD/install.sh"
                        )
                        brew_cmd = (
                            f'/bin/bash -c '
                            f'"$(curl -fsSL {brew_install_url})"'
                        )
                        result = run_with_spinner(
                            ['/bin/bash', '-c', brew_cmd],
                            "Installing Homebrew (this may take a few minutes)",
                            success_msg="Homebrew installed!",
                            error_msg="Failed to install Homebrew"
                        )
                        if result.returncode == 0:
                            print()
                            # Update PATH for this session so brew can be found
                            update_shell_path_for_homebrew()

                            # Get brew path (should work now)
                            brew_path = get_brew_path()
                            if not brew_path:
                                print_error("Homebrew installed but brew command not found")
                                print_info("Try manually: eval \"$($(get_homebrew_prefix)/bin/brew shellenv)\"")
                                print_info("Then: brew install python@3.11 && python3.11 setup.py")
                                sys.exit(1)

                            # Now install Python 3.11
                            result = run_with_spinner(
                                [brew_path, 'install', 'python@3.11'],
                                "Installing Python 3.11 (this may take a few minutes)",
                                success_msg="Python 3.11 installed!",
                                error_msg="Failed to install Python 3.11"
                            )
                            if result.returncode == 0:
                                reexec_with_python311()
                    except Exception as e:
                        print_error(f"Installation failed: {e}")
                        brew_manual = (
                            'Try manually: /bin/bash -c '
                            '"$(curl -fsSL https://raw.githubusercontent.com'
                            '/Homebrew/install/HEAD/install.sh)"'
                        )
                        print_info(brew_manual)
                        print_info(
                            "Then: brew install python@3.11 "
                            "&& python3.11 setup.py"
                        )
                else:
                    print_info("To install manually:")
                    brew_step1 = (
                        '  1. /bin/bash -c '
                        '"$(curl -fsSL https://raw.githubusercontent.com'
                        '/Homebrew/install/HEAD/install.sh)"'
                    )
                    print_info(brew_step1)
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
        subprocess.run(
            [str(pip_path), 'install', '--upgrade', 'pip'],
            capture_output=True, check=False
        )

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
        subprocess.run(
            [str(pip_path), 'install', package_name],
            capture_output=True, check=True
        )
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


def check_git_installed():
    """Check if git is installed (required for version display in frontend)"""
    try:
        subprocess.run(['git', '--version'], capture_output=True, check=True)
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
                last_seen_failed_count INTEGER DEFAULT 0,
                terms_accepted_at DATETIME,
                totp_secret TEXT DEFAULT NULL,
                mfa_enabled INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login_at DATETIME
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)")

        # Trusted devices table (MFA remember device for 30 days)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trusted_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                device_id TEXT UNIQUE NOT NULL,
                device_name TEXT,
                ip_address TEXT,
                location TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_trusted_devices_user_id ON trusted_devices(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_trusted_devices_device_id ON trusted_devices(device_id)")

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
                last_used_at DATETIME,
                auto_buy_enabled BOOLEAN DEFAULT 0,
                auto_buy_check_interval_minutes INTEGER DEFAULT 5,
                auto_buy_order_type TEXT DEFAULT 'market',
                auto_buy_usd_enabled BOOLEAN DEFAULT 0,
                auto_buy_usd_min REAL DEFAULT 10.0,
                auto_buy_usdc_enabled BOOLEAN DEFAULT 0,
                auto_buy_usdc_min REAL DEFAULT 0.0,
                auto_buy_usdt_enabled BOOLEAN DEFAULT 0,
                auto_buy_usdt_min REAL DEFAULT 0.0,
                is_paper_trading BOOLEAN DEFAULT 0,
                paper_balances TEXT,
                perps_portfolio_uuid TEXT,
                default_leverage INTEGER DEFAULT 1,
                margin_type TEXT DEFAULT 'CROSS'
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_accounts_user_id ON accounts(user_id)")

        # Bots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                name TEXT,
                description TEXT,
                account_id INTEGER REFERENCES accounts(id),
                exchange_type TEXT DEFAULT 'cex',
                market_type TEXT DEFAULT 'spot',
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
                reserved_usd_for_longs REAL DEFAULT 0.0,
                reserved_btc_for_shorts REAL DEFAULT 0.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_signal_check DATETIME,
                last_ai_check DATETIME
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_bots_user_id ON bots(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_bots_name ON bots(name)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_bot_user_name ON bots(user_id, name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_bots_strategy_type ON bots(strategy_type)")

        # Bot templates table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                name TEXT,
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

        # Bot products junction table (normalized trading pairs)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bot_id, product_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bot_products_bot_id ON bot_products(bot_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bot_products_product_id ON bot_products(product_id)")

        # Bot template products junction table (normalized trading pairs)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_template_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL REFERENCES bot_templates(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(template_id, product_id)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_bot_template_products_template_id "
            "ON bot_template_products(template_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_bot_template_products_product_id "
            "ON bot_template_products(product_id)"
        )

        # Positions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER REFERENCES bots(id),
                account_id INTEGER REFERENCES accounts(id),
                user_id INTEGER REFERENCES users(id),
                user_deal_number INTEGER,
                product_id TEXT DEFAULT 'ETH-BTC',
                status TEXT DEFAULT 'open',
                opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                closed_at DATETIME,
                direction TEXT DEFAULT 'long',
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
                entry_price REAL,
                short_entry_price REAL,
                short_average_sell_price REAL,
                short_total_sold_quote REAL,
                short_total_sold_base REAL,
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
                exit_reason TEXT,
                previous_indicators TEXT,
                user_attempt_number INTEGER,
                product_type TEXT DEFAULT 'spot',
                leverage INTEGER,
                perps_margin_type TEXT,
                liquidation_price REAL,
                funding_fees_total REAL DEFAULT 0.0,
                tp_order_id TEXT,
                sl_order_id TEXT,
                tp_price REAL,
                sl_price REAL,
                unrealized_pnl REAL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_positions_user_id ON positions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_positions_user_deal_number ON positions(user_deal_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_positions_user_attempt_number ON positions(user_attempt_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_direction ON positions(direction)")

        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER REFERENCES positions(id) ON DELETE CASCADE,
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
                remaining_base_amount REAL,
                time_in_force TEXT NOT NULL DEFAULT 'gtc',
                end_time DATETIME,
                is_manual BOOLEAN NOT NULL DEFAULT 0,
                reserved_amount_quote REAL DEFAULT 0.0,
                reserved_amount_base REAL DEFAULT 0.0
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

        # News articles table (cached news with local image storage)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                published_at DATETIME,
                summary TEXT,
                author TEXT,
                original_thumbnail_url TEXT,
                cached_thumbnail_path TEXT,
                image_data TEXT,
                category TEXT NOT NULL DEFAULT 'CryptoCurrency',
                source_id INTEGER REFERENCES content_sources(id),
                fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                has_issue BOOLEAN DEFAULT 0,
                content TEXT,
                content_fetched_at DATETIME,
                content_fetch_failed BOOLEAN DEFAULT 0
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_news_articles_url ON news_articles(url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_news_articles_published_at ON news_articles(published_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_news_articles_fetched_at ON news_articles(fetched_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_articles_category ON news_articles(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_news_articles_source_id ON news_articles(source_id)")

        # Video articles table (cached YouTube videos)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                video_id TEXT NOT NULL,
                source TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                published_at DATETIME,
                description TEXT,
                thumbnail_url TEXT,
                category TEXT NOT NULL DEFAULT 'CryptoCurrency',
                source_id INTEGER REFERENCES content_sources(id),
                fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_video_articles_url ON video_articles(url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_video_articles_video_id ON video_articles(video_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_video_articles_published_at ON video_articles(published_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_video_articles_fetched_at ON video_articles(fetched_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_video_articles_source ON video_articles(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_articles_category ON video_articles(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_video_articles_source_id ON video_articles(source_id)")

        # AI provider credentials table (per-user AI API keys)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_provider_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                api_key TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_used_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_ai_provider_credentials_user_id "
            "ON ai_provider_credentials(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_ai_provider_credentials_provider "
            "ON ai_provider_credentials(provider)"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "ix_ai_provider_credentials_user_provider "
            "ON ai_provider_credentials(user_id, provider)"
        )

        # Indicator logs table (for indicator-based condition evaluation logging)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indicator_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                product_id VARCHAR NOT NULL,
                phase VARCHAR NOT NULL,
                conditions_met BOOLEAN NOT NULL,
                conditions_detail JSON NOT NULL,
                indicators_snapshot JSON,
                current_price FLOAT,
                FOREIGN KEY (bot_id) REFERENCES bots(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_indicator_logs_bot_id ON indicator_logs(bot_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_indicator_logs_timestamp ON indicator_logs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_indicator_logs_product_id ON indicator_logs(product_id)")

        # Content sources table (news articles + video channels)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS content_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                url TEXT NOT NULL,
                website TEXT,
                description TEXT,
                channel_id TEXT,
                is_system BOOLEAN DEFAULT 1,
                is_enabled BOOLEAN DEFAULT 1,
                category TEXT NOT NULL DEFAULT 'CryptoCurrency',
                user_id INTEGER REFERENCES users(id),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_content_sources_type ON content_sources(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_content_sources_is_enabled ON content_sources(is_enabled)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_sources_category ON content_sources(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_content_sources_user_id ON content_sources(user_id)")

        # User source subscriptions (per-user preferences)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_source_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                source_id INTEGER NOT NULL,
                is_subscribed BOOLEAN DEFAULT 1,
                user_category TEXT,
                retention_days INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (source_id) REFERENCES content_sources(id) ON DELETE CASCADE,
                UNIQUE(user_id, source_id)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS "
            "ix_user_source_subscriptions_user_id "
            "ON user_source_subscriptions(user_id)"
        )

        # TTS persistence tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS article_tts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL
                    REFERENCES news_articles(id) ON DELETE CASCADE,
                voice_id TEXT NOT NULL,
                audio_path TEXT NOT NULL,
                word_timings TEXT,
                file_size_bytes INTEGER,
                content_hash TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by_user_id INTEGER REFERENCES users(id),
                UNIQUE(article_id, voice_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_voice_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                voice_id TEXT NOT NULL,
                is_enabled BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, voice_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_article_tts_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                article_id INTEGER NOT NULL
                    REFERENCES news_articles(id) ON DELETE CASCADE,
                last_voice_id TEXT NOT NULL,
                last_played_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, article_id)
            )
        """)

        # User content seen/read status (articles & videos)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_content_seen_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                content_type TEXT NOT NULL,
                content_id INTEGER NOT NULL,
                seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, content_type, content_id)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_user_content_seen_lookup "
            "ON user_content_seen_status(user_id, content_type)"
        )

        # Account value snapshots (daily historical tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account_value_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                snapshot_date DATETIME NOT NULL,
                total_value_btc REAL NOT NULL DEFAULT 0.0,
                total_value_usd REAL NOT NULL DEFAULT 0.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(account_id, snapshot_date)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS "
            "idx_account_value_snapshots_account_id "
            "ON account_value_snapshots(account_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS "
            "idx_account_value_snapshots_user_id "
            "ON account_value_snapshots(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS "
            "idx_account_value_snapshots_date "
            "ON account_value_snapshots(snapshot_date)"
        )

        # Metric snapshots table (for sparkline charts on market sentiment cards)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metric_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL,
                recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_metric_snapshots_metric_name ON metric_snapshots(metric_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_metric_snapshots_recorded_at ON metric_snapshots(recorded_at)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_metric_snapshots_name_time "
            "ON metric_snapshots(metric_name, recorded_at)"
        )

        # Seed default content sources
        # Format: (source_key, name, type, url, website, description, channel_id, category)
        default_sources = [
            # ===== CryptoCurrency News =====
            (
                'reddit_crypto',
                'Reddit r/CryptoCurrency',
                'news',
                'https://www.reddit.com/r/CryptoCurrency/hot.json?limit=15',
                'https://www.reddit.com/r/CryptoCurrency',
                'Community-driven crypto discussion',
                None,
                'CryptoCurrency',
            ),
            (
                'reddit_bitcoin',
                'Reddit r/Bitcoin',
                'news',
                'https://www.reddit.com/r/Bitcoin/hot.json?limit=10',
                'https://www.reddit.com/r/Bitcoin',
                'Bitcoin-focused community news',
                None,
                'CryptoCurrency',
            ),
            (
                'bitcoin_magazine',
                'Bitcoin Magazine',
                'news',
                'https://bitcoinmagazine.com/feed',
                'https://bitcoinmagazine.com',
                'Bitcoin news, analysis & culture',
                None,
                'CryptoCurrency',
            ),
            (
                'beincrypto',
                'BeInCrypto',
                'news',
                'https://beincrypto.com/feed/',
                'https://beincrypto.com',
                'Crypto news, guides & price analysis',
                None,
                'CryptoCurrency',
            ),
            (
                'blockworks',
                'Blockworks',
                'news',
                'https://blockworks.co/feed',
                'https://blockworks.co',
                'Crypto & DeFi institutional news',
                None,
                'CryptoCurrency',
            ),
            (
                'coindesk',
                'CoinDesk',
                'news',
                'https://www.coindesk.com/arc/outboundfeeds/rss/',
                'https://www.coindesk.com',
                'Crypto news & analysis',
                None,
                'CryptoCurrency',
            ),
            (
                'cointelegraph',
                'CoinTelegraph',
                'news',
                'https://cointelegraph.com/rss',
                'https://cointelegraph.com',
                'Blockchain & crypto news',
                None,
                'CryptoCurrency',
            ),
            (
                'decrypt',
                'Decrypt',
                'news',
                'https://decrypt.co/feed',
                'https://decrypt.co',
                'Web3 news & guides',
                None,
                'CryptoCurrency',
            ),
            (
                'theblock',
                'The Block',
                'news',
                'https://www.theblock.co/rss.xml',
                'https://www.theblock.co',
                'Institutional crypto news',
                None,
                'CryptoCurrency',
            ),
            (
                'cryptoslate',
                'CryptoSlate',
                'news',
                'https://cryptoslate.com/feed/',
                'https://cryptoslate.com',
                'Crypto news & data',
                None,
                'CryptoCurrency',
            ),
            # CryptoCurrency Video sources
            (
                'coin_bureau',
                'Coin Bureau',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCqK_GSMbpiV8spgD3ZGloSw',
                'https://www.youtube.com/@CoinBureau',
                'Educational crypto content & analysis',
                'UCqK_GSMbpiV8spgD3ZGloSw',
                'CryptoCurrency',
            ),
            (
                'benjamin_cowen',
                'Benjamin Cowen',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCRvqjQPSeaWn-uEx-w0XOIg',
                'https://www.youtube.com/@intothecryptoverse',
                'Technical analysis & market cycles',
                'UCRvqjQPSeaWn-uEx-w0XOIg',
                'CryptoCurrency',
            ),
            (
                'altcoin_daily',
                'Altcoin Daily',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCbLhGKVY-bJPcawebgtNfbw',
                'https://www.youtube.com/@AltcoinDaily',
                'Daily crypto news & updates',
                'UCbLhGKVY-bJPcawebgtNfbw',
                'CryptoCurrency',
            ),
            (
                'bankless',
                'Bankless',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCAl9Ld79qaZxp9JzEOwd3aA',
                'https://www.youtube.com/@Bankless',
                'Ethereum & DeFi ecosystem',
                'UCAl9Ld79qaZxp9JzEOwd3aA',
                'CryptoCurrency',
            ),
            (
                'the_defiant',
                'The Defiant',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCL0J4MLEdLP0-UyLu0hCktg',
                'https://www.youtube.com/@TheDefiant',
                'DeFi news & interviews',
                'UCL0J4MLEdLP0-UyLu0hCktg',
                'CryptoCurrency',
            ),
            (
                'crypto_banter',
                'Crypto Banter',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCN9Nj4tjXbVTLYWN0EKly_Q',
                'https://www.youtube.com/@CryptoBanter',
                'Live crypto shows & trading',
                'UCN9Nj4tjXbVTLYWN0EKly_Q',
                'CryptoCurrency',
            ),
            (
                'datadash',
                'DataDash',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCCatR7nWbYrkVXdxXb4cGXw',
                'https://www.youtube.com/@DataDash',
                'Macro markets & crypto analysis',
                'UCCatR7nWbYrkVXdxXb4cGXw',
                'CryptoCurrency',
            ),
            (
                'cryptosrus',
                'CryptosRUs',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCI7M65p3A-D3P4v5qW8POxQ',
                'https://www.youtube.com/@CryptosRUs',
                'Market analysis & project reviews',
                'UCI7M65p3A-D3P4v5qW8POxQ',
                'CryptoCurrency',
            ),
            (
                'the_moon',
                'The Moon',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCc4Rz_T9Sb1w5rqqo9pL1Og',
                'https://www.youtube.com/@TheMoonCarl',
                'Daily Bitcoin analysis & news',
                'UCc4Rz_T9Sb1w5rqqo9pL1Og',
                'CryptoCurrency',
            ),
            (
                'digital_asset_news',
                'Digital Asset News',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCJgHxpqfhWEEjYH9cLXqhIQ',
                'https://www.youtube.com/@DigitalAssetNews',
                'Bite-sized crypto news updates',
                'UCJgHxpqfhWEEjYH9cLXqhIQ',
                'CryptoCurrency',
            ),
            (
                'paul_barron',
                'Paul Barron Network',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UC4VPa7EOvObpyCRI4YKRQRw',
                'https://www.youtube.com/@paulbarronnetwork',
                'Tech, AI & crypto intersection',
                'UC4VPa7EOvObpyCRI4YKRQRw',
                'CryptoCurrency',
            ),
            (
                'lark_davis',
                'Lark Davis',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCl2oCaw8hdR_kbqyqd2klIA',
                'https://www.youtube.com/@TheCryptoLark',
                'Altcoin analysis & opportunities',
                'UCl2oCaw8hdR_kbqyqd2klIA',
                'CryptoCurrency',
            ),
            (
                'pompliano',
                'Anthony Pompliano',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCevXpeL8cNyAnww-NqJ4m2w',
                'https://www.youtube.com/@AnthonyPompliano',
                'Bitcoin advocate & market commentary',
                'UCevXpeL8cNyAnww-NqJ4m2w',
                'CryptoCurrency',
            ),
            (
                'whiteboard_crypto',
                'Whiteboard Crypto',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCsYYksPHiGqXHPoHI-fm5sg',
                'https://www.youtube.com/@WhiteboardCrypto',
                'Educational crypto explainers',
                'UCsYYksPHiGqXHPoHI-fm5sg',
                'CryptoCurrency',
            ),
            # ===== AI =====
            (
                'reddit_artificial',
                'Reddit r/artificial',
                'news',
                'https://www.reddit.com/r/artificial/hot.json?limit=15',
                'https://www.reddit.com/r/artificial',
                'AI community discussion',
                None,
                'AI',
            ),
            (
                'openai_blog',
                'OpenAI Blog',
                'news',
                'https://openai.com/blog/rss.xml',
                'https://openai.com/blog',
                'OpenAI research & announcements',
                None,
                'AI',
            ),
            (
                'mit_tech_ai',
                'MIT Tech Review AI',
                'news',
                'https://www.technologyreview.com/topic/artificial-intelligence/feed',
                'https://www.technologyreview.com/topic/artificial-intelligence',
                'MIT AI research coverage',
                None,
                'AI',
            ),
            (
                'the_ai_beat',
                'VentureBeat AI',
                'news',
                'https://venturebeat.com/category/ai/feed/',
                'https://venturebeat.com/category/ai',
                'Enterprise AI news',
                None,
                'AI',
            ),
            (
                'two_minute_papers',
                'Two Minute Papers',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCbfYPyITQ-7l4upoX8nvctg',
                'https://www.youtube.com/@TwoMinutePapers',
                'AI research explained in short videos',
                'UCbfYPyITQ-7l4upoX8nvctg',
                'AI',
            ),
            (
                'ai_explained',
                'AI Explained',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCNJ1Ymd5yFuUPtn21xtRbbw',
                'https://www.youtube.com/@aiaborz',
                'Clear AI news and explanations',
                'UCNJ1Ymd5yFuUPtn21xtRbbw',
                'AI',
            ),
            (
                'matt_wolfe',
                'Matt Wolfe',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCJtUOos_MwJa_Ewii-R3cJA',
                'https://www.youtube.com/@maborz',
                'AI tools, news & tutorials',
                'UCJtUOos_MwJa_Ewii-R3cJA',
                'AI',
            ),
            # ===== Finance =====
            (
                'reuters_finance',
                'Bloomberg Markets',
                'news',
                'https://feeds.bloomberg.com/markets/news.rss',
                'https://www.bloomberg.com/markets',
                'Bloomberg financial news',
                None,
                'Finance',
            ),
            (
                'ft_markets',
                'Financial Times',
                'news',
                'https://www.ft.com/markets?format=rss',
                'https://www.ft.com/markets',
                'Financial Times market coverage',
                None,
                'Finance',
            ),
            (
                'motley_fool',
                'Motley Fool',
                'news',
                'https://www.fool.com/feeds/index.aspx',
                'https://www.fool.com',
                'Investing analysis & stock picks',
                None,
                'Finance',
            ),
            (
                'the_economist_finance',
                'The Economist',
                'news',
                'https://www.economist.com/finance-and-economics/rss.xml',
                'https://www.economist.com',
                'Finance & economics analysis',
                None,
                'Finance',
            ),
            (
                'financial_times',
                'Financial Times',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCoUxsWakJucWg46KW5RsvPw',
                'https://www.youtube.com/@FinancialTimes',
                'Financial news and analysis',
                'UCoUxsWakJucWg46KW5RsvPw',
                'Finance',
            ),
            (
                'graham_stephan',
                'Graham Stephan',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCV6KDgJskWaEckne5aPA0aQ',
                'https://www.youtube.com/@GrahamStephan',
                'Personal finance & investing',
                'UCV6KDgJskWaEckne5aPA0aQ',
                'Finance',
            ),
            # ===== World =====
            (
                'guardian_world',
                'The Guardian World',
                'news',
                'https://www.theguardian.com/world/rss',
                'https://www.theguardian.com/world',
                'International news coverage',
                None,
                'World',
            ),
            (
                'bbc_world',
                'BBC World',
                'news',
                'https://feeds.bbci.co.uk/news/world/rss.xml',
                'https://www.bbc.com/news/world',
                'Global news from BBC',
                None,
                'World',
            ),
            (
                'al_jazeera',
                'Al Jazeera',
                'news',
                'https://www.aljazeera.com/xml/rss/all.xml',
                'https://www.aljazeera.com',
                'International news coverage',
                None,
                'World',
            ),
            (
                'wion',
                'WION',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCWEIPvoxRwn6llPOIn555rQ',
                'https://www.youtube.com/@WIONews',
                'World Is One News - international coverage',
                'UCWEIPvoxRwn6llPOIn555rQ',
                'World',
            ),
            (
                'dw_news',
                'DW News',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCknLrEdhRCp1aegoMqRaCZg',
                'https://www.youtube.com/@daborintv',
                'Deutsche Welle international news',
                'UCknLrEdhRCp1aegoMqRaCZg',
                'World',
            ),
            (
                'channel4_news',
                'Channel 4 News',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCTrQ7HXWRRxr7OsOtodr2_w',
                'https://www.youtube.com/@Channel4News',
                'UK-based international news coverage',
                'UCTrQ7HXWRRxr7OsOtodr2_w',
                'World',
            ),
            # ===== Nation (US) =====
            (
                'npr_news',
                'NPR News',
                'news',
                'https://feeds.npr.org/1001/rss.xml',
                'https://www.npr.org',
                'US national public radio news',
                None,
                'Nation',
            ),
            (
                'pbs_newshour',
                'PBS NewsHour',
                'news',
                'https://www.pbs.org/newshour/feeds/rss/headlines',
                'https://www.pbs.org/newshour',
                'In-depth US news',
                None,
                'Nation',
            ),
            (
                'ap_news',
                'AP News',
                'news',
                'https://feedx.net/rss/ap.xml',
                'https://apnews.com',
                'Associated Press top stories',
                None,
                'Nation',
            ),
            (
                'pbs_newshour_yt',
                'PBS NewsHour',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UC6ZFN9Tx6xh-skXCuRHCDpQ',
                'https://www.youtube.com/@PBSNewsHour',
                'In-depth US national news',
                'UC6ZFN9Tx6xh-skXCuRHCDpQ',
                'Nation',
            ),
            (
                'nbc_news',
                'NBC News',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCeY0bbntWzzVIaj2z3QigXg',
                'https://www.youtube.com/@NBCNews',
                'Major US network news',
                'UCeY0bbntWzzVIaj2z3QigXg',
                'Nation',
            ),
            (
                'abc_news',
                'ABC News',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCBi2mrWuNuyYy4gbM6fU18Q',
                'https://www.youtube.com/@ABCNews',
                'Major US network news',
                'UCBi2mrWuNuyYy4gbM6fU18Q',
                'Nation',
            ),
            # ===== Business =====
            (
                'cnbc_business',
                'CNBC',
                'news',
                'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147',
                'https://www.cnbc.com',
                'Business & financial news',
                None,
                'Business',
            ),
            (
                'marketwatch',
                'MarketWatch',
                'news',
                'https://www.marketwatch.com/rss/topstories',
                'https://www.marketwatch.com',
                'Financial markets & investing',
                None,
                'Business',
            ),
            (
                'wsj_markets',
                'WSJ Markets',
                'news',
                'https://feeds.a.dj.com/rss/RSSMarketsMain.xml',
                'https://www.wsj.com/news/markets',
                'Wall Street Journal market news',
                None,
                'Business',
            ),
            (
                'cnbc_yt',
                'CNBC',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCvJJ_dzjViJCoLf5uKUTwoA',
                'https://www.youtube.com/@CNBC',
                'Business and financial news',
                'UCvJJ_dzjViJCoLf5uKUTwoA',
                'Business',
            ),
            (
                'bloomberg',
                'Bloomberg Television',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCIALMKvObZNtJ6AmdCLP7Lg',
                'https://www.youtube.com/@bloombergtv',
                'Global business and financial news',
                'UCIALMKvObZNtJ6AmdCLP7Lg',
                'Business',
            ),
            (
                'yahoo_finance',
                'Yahoo Finance',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCEAZeUIeJs0IjQiqTCdVSIg',
                'https://www.youtube.com/@YahooFinance',
                'Financial news and market analysis',
                'UCEAZeUIeJs0IjQiqTCdVSIg',
                'Business',
            ),
            # ===== Technology =====
            (
                'engadget',
                'Engadget',
                'news',
                'https://www.engadget.com/rss.xml',
                'https://www.engadget.com',
                'Consumer tech news & reviews',
                None,
                'Technology',
            ),
            (
                'ars_technica',
                'Ars Technica',
                'news',
                'https://feeds.arstechnica.com/arstechnica/index',
                'https://arstechnica.com',
                'Technology news & analysis',
                None,
                'Technology',
            ),
            (
                'the_verge',
                'The Verge',
                'news',
                'https://www.theverge.com/rss/index.xml',
                'https://www.theverge.com',
                'Tech, science & culture',
                None,
                'Technology',
            ),
            (
                'wired',
                'Wired',
                'news',
                'https://www.wired.com/feed/rss',
                'https://www.wired.com',
                'Technology & future trends',
                None,
                'Technology',
            ),
            (
                'mkbhd',
                'Marques Brownlee',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCBJycsmduvYEL83R_U4JriQ',
                'https://www.youtube.com/@mkbhd',
                'Tech reviews and commentary',
                'UCBJycsmduvYEL83R_U4JriQ',
                'Technology',
            ),
            (
                'linus_tech_tips',
                'Linus Tech Tips',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCXuqSBlHAE6Xw-yeJA0Tunw',
                'https://www.youtube.com/@LinusTechTips',
                'Tech reviews and builds',
                'UCXuqSBlHAE6Xw-yeJA0Tunw',
                'Technology',
            ),
            (
                'the_verge_yt',
                'The Verge',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCddiUEpeqJcYeBxX1IVBKvQ',
                'https://www.youtube.com/@TheVerge',
                'Technology news and reviews',
                'UCddiUEpeqJcYeBxX1IVBKvQ',
                'Technology',
            ),
            # ===== Entertainment =====
            (
                'variety',
                'Variety',
                'news',
                'https://variety.com/feed/',
                'https://variety.com',
                'Entertainment industry news',
                None,
                'Entertainment',
            ),
            (
                'hollywood_reporter',
                'Hollywood Reporter',
                'news',
                'https://www.hollywoodreporter.com/feed/',
                'https://www.hollywoodreporter.com',
                'Movies, TV & entertainment',
                None,
                'Entertainment',
            ),
            (
                'deadline',
                'Deadline',
                'news',
                'https://deadline.com/feed/',
                'https://deadline.com',
                'Entertainment industry breaking news',
                None,
                'Entertainment',
            ),
            (
                'screen_junkies',
                'Screen Junkies',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCOpcACMWblDls9Z6GERVi1A',
                'https://www.youtube.com/@ScreenJunkies',
                'Movie commentary and Honest Trailers',
                'UCOpcACMWblDls9Z6GERVi1A',
                'Entertainment',
            ),
            (
                'collider',
                'Collider',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UC5hX0jtOEAobccb2dvSnYbw',
                'https://www.youtube.com/@Collider',
                'Movies and TV discussion',
                'UC5hX0jtOEAobccb2dvSnYbw',
                'Entertainment',
            ),
            (
                'ign',
                'IGN',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCKy1dAqELo0zrOtPkf0eTMw',
                'https://www.youtube.com/@IGN',
                'Gaming and entertainment news',
                'UCKy1dAqELo0zrOtPkf0eTMw',
                'Entertainment',
            ),
            # ===== Sports =====
            (
                'espn',
                'ESPN',
                'news',
                'https://www.espn.com/espn/rss/news',
                'https://www.espn.com',
                'Sports news & scores',
                None,
                'Sports',
            ),
            (
                'cbs_sports',
                'CBS Sports',
                'news',
                'https://www.cbssports.com/rss/headlines/',
                'https://www.cbssports.com',
                'Sports news & scores',
                None,
                'Sports',
            ),
            (
                'yahoo_sports',
                'Yahoo Sports',
                'news',
                'https://sports.yahoo.com/rss/',
                'https://sports.yahoo.com',
                'Sports news & analysis',
                None,
                'Sports',
            ),
            (
                'espn_yt',
                'ESPN',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCiWLfSweyRNmLpgEHekhoAg',
                'https://www.youtube.com/@espn',
                'Sports news and highlights',
                'UCiWLfSweyRNmLpgEHekhoAg',
                'Sports',
            ),
            (
                'cbs_sports_yt',
                'CBS Sports',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCja8sZ2T4ylIqjggA1Zuukg',
                'https://www.youtube.com/@CBSSports',
                'Sports coverage and analysis',
                'UCja8sZ2T4ylIqjggA1Zuukg',
                'Sports',
            ),
            (
                'pat_mcafee',
                'The Pat McAfee Show',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCxcTeAKWJca6XyJ37_ZoKIQ',
                'https://www.youtube.com/@ThePatMcAfeeShow',
                'Sports talk and commentary',
                'UCxcTeAKWJca6XyJ37_ZoKIQ',
                'Sports',
            ),
            # ===== Science =====
            (
                'science_daily',
                'Science Daily',
                'news',
                'https://www.sciencedaily.com/rss/all.xml',
                'https://www.sciencedaily.com',
                'Breaking science news',
                None,
                'Science',
            ),
            (
                'nasa',
                'NASA',
                'news',
                'https://www.nasa.gov/rss/dyn/breaking_news.rss',
                'https://www.nasa.gov',
                'Space & science updates',
                None,
                'Science',
            ),
            (
                'new_scientist',
                'New Scientist',
                'news',
                'https://www.newscientist.com/feed/home/',
                'https://www.newscientist.com',
                'Science & technology news',
                None,
                'Science',
            ),
            (
                'veritasium',
                'Veritasium',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCHnyfMqiRRG1u-2MsSQLbXA',
                'https://www.youtube.com/@veritasium',
                'Science education and experiments',
                'UCHnyfMqiRRG1u-2MsSQLbXA',
                'Science',
            ),
            (
                'kurzgesagt',
                'Kurzgesagt',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCsXVk37bltHxD1rDPwtNM8Q',
                'https://www.youtube.com/@kurzgesagt',
                'Animated science explainers',
                'UCsXVk37bltHxD1rDPwtNM8Q',
                'Science',
            ),
            (
                'smarter_every_day',
                'SmarterEveryDay',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UC6107grRI4m0o2-emgoDnAA',
                'https://www.youtube.com/@smartereveryday',
                'Science and engineering exploration',
                'UC6107grRI4m0o2-emgoDnAA',
                'Science',
            ),
            # ===== Health =====
            (
                'stat_news',
                'STAT News',
                'news',
                'https://www.statnews.com/feed/',
                'https://www.statnews.com',
                'Health & pharma reporting',
                None,
                'Health',
            ),
            (
                'npr_health',
                'NPR Health',
                'news',
                'https://feeds.npr.org/103537970/rss.xml',
                'https://www.npr.org/sections/health',
                'Public health news',
                None,
                'Health',
            ),
            (
                'science_daily_health',
                'Science Daily Health',
                'news',
                'https://www.sciencedaily.com/rss/health_medicine.xml',
                'https://www.sciencedaily.com',
                'Health & medicine research',
                None,
                'Health',
            ),
            (
                'the_lancet',
                'The Lancet',
                'news',
                'https://www.thelancet.com/rssfeed/lancet_online.xml',
                'https://www.thelancet.com',
                'Medical journal articles',
                None,
                'Health',
            ),
            (
                'nature_medicine',
                'Nature Medicine',
                'news',
                'https://www.nature.com/nm.rss',
                'https://www.nature.com/nm',
                'Medical research journal',
                None,
                'Health',
            ),
            (
                'genetic_engineering_news',
                'Genetic Engineering News',
                'news',
                'https://www.genengnews.com/feed/',
                'https://www.genengnews.com',
                'Genetics & biotech news',
                None,
                'Health',
            ),
            (
                'who_news',
                'WHO News',
                'news',
                'https://www.who.int/rss-feeds/news-english.xml',
                'https://www.who.int',
                'World Health Organization',
                None,
                'Health',
            ),
            (
                'nutrition_org',
                'Nutrition.org',
                'news',
                'https://nutrition.org/feed/',
                'https://nutrition.org',
                'Nutrition science & research',
                None,
                'Health',
            ),
            (
                'self_wellness',
                'SELF',
                'news',
                'https://www.self.com/feed/rss',
                'https://www.self.com',
                'Wellness & fitness',
                None,
                'Health',
            ),
            (
                'doctor_mike',
                'Doctor Mike',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UC0QHWhjbe5fGJEPz3sVb6nw',
                'https://www.youtube.com/@DoctorMike',
                'Medical education and health advice',
                'UC0QHWhjbe5fGJEPz3sVb6nw',
                'Health',
            ),
            (
                'medlife_crisis',
                'Medlife Crisis',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UCgRBRE1DUP2w7HTH9j_L4OQ',
                'https://www.youtube.com/@MedlifeCrisis',
                'Medical topics from a cardiologist',
                'UCgRBRE1DUP2w7HTH9j_L4OQ',
                'Health',
            ),
            (
                'dr_eric_berg',
                'Dr. Eric Berg DC',
                'video',
                'https://www.youtube.com/feeds/videos.xml?channel_id=UC3w193M5tYPJqF0Hi-7U-2g',
                'https://www.youtube.com/@drberg',
                'Health and nutrition advice',
                'UC3w193M5tYPJqF0Hi-7U-2g',
                'Health',
            ),
        ]
        for source in default_sources:
            cursor.execute(
                "INSERT OR IGNORE INTO content_sources "
                "(source_key, name, type, url, website, "
                "description, channel_id, category) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                source
            )

        conn.commit()
        print_success("Database tables created")
        return True

    except Exception as e:
        conn.rollback()
        print_error(f"Failed to initialize database: {e}")
        return False
    finally:
        conn.close()


def get_existing_admin_user(project_root):
    """Get existing admin user info from database if exists

    Returns:
        tuple: (email, display_name) or (None, None) if no admin exists
    """
    db_path = project_root / 'backend' / 'trading.db'

    if not db_path.exists():
        return None, None

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get first admin user
        cursor.execute("""
            SELECT email, display_name
            FROM users
            WHERE is_superuser = 1
            ORDER BY created_at
            LIMIT 1
        """)
        result = cursor.fetchone()
        conn.close()

        if result:
            return result[0], result[1]
    except Exception:
        pass

    return None, None


def create_admin_user(project_root, email, password, display_name=None):
    """Create the initial admin user and return the user_id"""
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
        return None

    hashed = result.stdout.strip()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if user already exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (email.lower(),))
        existing = cursor.fetchone()

        if existing:
            print_warning(f"User {email} already exists")
            return existing[0]  # Return existing user_id

        cursor.execute("""
            INSERT INTO users (email, hashed_password, is_active, is_superuser, display_name, created_at, updated_at)
            VALUES (?, ?, 1, 1, ?, ?, ?)
        """, (email.lower(), hashed, display_name, datetime.utcnow(), datetime.utcnow()))

        user_id = cursor.lastrowid
        conn.commit()
        print_success(f"Admin user '{email}' created")
        return user_id

    except Exception as e:
        conn.rollback()
        print_error(f"Failed to create admin user: {e}")
        return None
    finally:
        conn.close()


def seed_coin_categorizations(project_root, user_id):
    """Seed initial coin categorizations with AI-reviewed safety assessments"""
    db_path = project_root / 'backend' / 'trading.db'

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if any GLOBAL categorizations already exist (user_id IS NULL)
        cursor.execute("SELECT COUNT(*) FROM blacklisted_coins WHERE user_id IS NULL")
        existing_count = cursor.fetchone()[0]

        if existing_count > 0:
            print_info(f"Global coin categorizations already exist ({existing_count} coins)")
            return True

        # Comprehensive coin categorizations - essential [APPROVED] coins and major [MEME] coins
        # Full production database has 361 coins; this includes most important ones
        coin_categories = [
            ('1INCH', '[APPROVED] DEX aggregator, useful DeFi tool'),
            ('AAVE', '[APPROVED] Leading DeFi lending platform'),
            ('ADA', '[APPROVED] Solid tech, active development'),
            ('ALGO', '[APPROVED] Fast, secure blockchain'),
            ('APT', '[APPROVED] New blockchain, promising tech'),
            ('ARB', '[APPROVED] Ethereum Layer 2 scaling solution'),
            ('ATOM', '[APPROVED] Cosmos, internet of blockchains'),
            ('AVAX', '[APPROVED] Fast, scalable blockchain'),
            ('BAL', '[APPROVED] DEX, automated portfolio manager'),
            ('BAT', '[APPROVED] Brave browser integration, privacy focus'),
            ('BNB', '[APPROVED] Binance ecosystem, high utility'),
            ('BTC', '[APPROVED] Dominant cryptocurrency, store of value'),
            ('CBETH', '[APPROVED] Coinbase ETH staking derivative'),
            ('COMP', '[APPROVED] DeFi lending protocol, established'),
            ('CRV', '[APPROVED] Curve Finance governance token, DeFi'),
            ('CVX', '[APPROVED] Convex Finance, boosts CRV rewards'),
            ('DAI', '[APPROVED] Decentralized stablecoin, widely used'),
            ('DOT', '[APPROVED] Solid tech, parachains, active development'),
            ('ENS', '[APPROVED] Decentralized naming, growing adoption'),
            ('ETH', '[APPROVED] #2 crypto, massive ecosystem, DeFi foundation'),
            ('EURC', '[APPROVED] Euro-backed stablecoin, regulated'),
            ('FET', '[APPROVED] AI focus, solid partnerships, growing use'),
            ('GNO', '[APPROVED] Solid tech, DAO tooling, active dev'),
            ('GRT', '[APPROVED] Indexing protocol, growing adoption'),
            ('HBAR', '[APPROVED] Hashgraph tech, enterprise focus'),
            ('ILV', '[APPROVED] Gaming/NFT project, active development'),
            ('IMX', '[APPROVED] Layer-2 scaling for NFTs, strong partnerships'),
            ('INJ', '[APPROVED] DeFi focused blockchain, growing ecosystem'),
            ('IOTX', '[APPROVED] Decentralized IoT platform, real-world use'),
            ('JUPITER', '[APPROVED] Solana DEX aggregator, high volume'),
            ('KAVA', '[APPROVED] Cross-chain DeFi platform, growing TVL'),
            ('KSM', "[APPROVED] Polkadot's canary network, innovation"),
            ('LDO', '[APPROVED] Lido DAO, liquid staking dominance'),
            ('LINK', '[APPROVED] Decentralized oracle network, essential'),
            ('LPT', '[APPROVED] Livepeer, decentralized video streaming'),
            ('LQTY', '[APPROVED] Decentralized borrowing protocol'),
            ('LTC', '[APPROVED] Established cryptocurrency, payment focus'),
            ('MAGIC', '[APPROVED] Gaming ecosystem, active development'),
            ('MANA', '[APPROVED] Decentraland, metaverse platform'),
            ('MANTLE', '[APPROVED] Ethereum Layer-2, growing ecosystem'),
            ('MASK', '[APPROVED] Web3 social protocol, privacy focus'),
            ('METIS', '[APPROVED] Ethereum Layer-2, growing ecosystem'),
            ('MINA', '[APPROVED] Succinct blockchain, privacy focus'),
            ('MKR', '[APPROVED] Governance token for MakerDAO, stablecoin leader'),
            ('MORPHO', '[APPROVED] Optimized DeFi lending, growing TVL'),
            ('NEAR', '[APPROVED] Scalable blockchain, active development'),
            ('OCEAN', '[APPROVED] Data sharing protocol, growing ecosystem'),
            ('ONDO', '[APPROVED] Tokenized real-world assets, institutional focus'),
            ('OP', '[APPROVED] Optimism L2 scaling solution, growing ecosystem'),
            ('ORCA', '[APPROVED] Solana DEX, strong performance'),
            ('OSMO', '[APPROVED] Cosmos DEX, interchain focus'),
            ('PAX', '[APPROVED] Stablecoin, regulated, reliable'),
            ('PAXG', '[APPROVED] Gold-backed token, stable value'),
            ('PENDLE', '[APPROVED] Yield trading protocol, innovative DeFi'),
            ('PERP', '[APPROVED] Perpetual futures DEX, growing adoption'),
            ('PNG', '[APPROVED] Avalanche DEX, established platform'),
            ('PYTH', '[APPROVED] Decentralized financial data, growing adoption'),
            ('QNT', '[APPROVED] Interoperability focus, strong partnerships'),
            ('RENDER', '[APPROVED] Decentralized GPU rendering, growing demand'),
            ('RONIN', '[APPROVED] Gaming blockchain, strong ecosystem'),
            ('RPL', '[APPROVED] Ethereum staking infrastructure, solid utility'),
            ('SAND', '[APPROVED] Metaverse platform, established presence'),
            ('SNX', '[APPROVED] Derivatives platform, established DeFi'),
            ('SOL', '[APPROVED] Fast blockchain, growing ecosystem'),
            ('STORJ', '[APPROVED] Decentralized storage, real-world use'),
            ('STX', '[APPROVED] Bitcoin L2, growing ecosystem'),
            ('TAO', '[APPROVED] Decentralized AI compute network, strong growth'),
            ('TIA', '[APPROVED] Modular blockchain, promising tech'),
            ('TON', '[APPROVED] Telegram-integrated blockchain, growing ecosystem'),
            ('UMA', '[APPROVED] Synthetic assets, established DeFi project'),
            ('UNI', '[APPROVED] Leading DEX, strong governance'),
            ('USDT', '[APPROVED] Dominant stablecoin, high liquidity'),
            ('VET', '[APPROVED] Supply chain blockchain, enterprise adoption'),
            ('WLD', '[APPROVED] Worldcoin, identity protocol, controversial'),
            ('XLM', '[APPROVED] Fast, cheap payments, established network'),
            ('XRP', '[APPROVED] Payment protocol, regulatory uncertainty'),
            ('YFI', '[APPROVED] Yield farming aggregator, established DeFi'),
            ('ZRX', '[APPROVED] Decentralized exchange protocol, established project'),
            ('DOGE', '[MEME] Original meme coin, community-driven'),
            ('PEPE', '[MEME] Popular meme coin, high volatility'),
            ('SHIB', '[MEME] Popular meme coin, high volatility'),
            ('BONK', '[MEME] Solana meme coin, community-driven'),
            ('FLOKI', '[MEME] Meme coin, speculative, high risk'),
        ]

        # Insert all categorizations as GLOBAL entries (user_id = NULL)
        # These are visible to all users and managed by admins only
        for symbol, reason in coin_categories:
            cursor.execute("""
                INSERT OR IGNORE INTO blacklisted_coins (user_id, symbol, reason, created_at)
                VALUES (?, ?, ?, ?)
            """, (None, symbol, reason, datetime.utcnow()))

        conn.commit()
        print_success(f"Seeded {len(coin_categories)} coin categorizations")
        return True

    except Exception as e:
        conn.rollback()
        print_error(f"Failed to seed coin categorizations: {e}")
        return False
    finally:
        conn.close()


def create_coinbase_account(project_root, user_id, api_key_name, api_private_key):
    """Create a Coinbase exchange account for the user in the database"""
    db_path = project_root / 'backend' / 'trading.db'

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if user already has a Coinbase account
        cursor.execute("""
            SELECT id FROM accounts
            WHERE user_id = ? AND type = 'cex' AND exchange = 'coinbase'
        """, (user_id,))
        existing = cursor.fetchone()

        if existing:
            # Update existing account
            cursor.execute("""
                UPDATE accounts
                SET api_key_name = ?, api_private_key = ?, updated_at = ?
                WHERE id = ?
            """, (api_key_name, api_private_key, datetime.utcnow(), existing[0]))
            print_success("Coinbase account credentials updated")
        else:
            # Create new account
            cursor.execute("""
                INSERT INTO accounts (user_id, name, type, exchange, api_key_name, api_private_key,
                                     is_default, is_active, created_at, updated_at)
                VALUES (?, 'Coinbase (Primary)', 'cex', 'coinbase', ?, ?, 1, 1, ?, ?)
            """, (user_id, api_key_name, api_private_key, datetime.utcnow(), datetime.utcnow()))
            print_success("Coinbase account created")

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        print_error(f"Failed to create Coinbase account: {e}")
        return False
    finally:
        conn.close()


def create_paper_trading_account(project_root, user_id):
    """Create a default paper trading account for the user"""
    db_path = project_root / 'backend' / 'trading.db'

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if user already has a paper trading account
        cursor.execute("""
            SELECT id FROM accounts
            WHERE user_id = ? AND is_paper_trading = 1
        """, (user_id,))
        existing = cursor.fetchone()

        if existing:
            print_info("Paper trading account already exists")
            return True

        # Create paper trading account with initial balances
        import json
        initial_balances = json.dumps({
            "BTC": 0.01,      # Start with 0.01 BTC
            "ETH": 0.0,
            "USD": 1000.0,    # Start with $1000 USD
            "USDC": 0.0,
            "USDT": 0.0
        })

        cursor.execute("""
            INSERT INTO accounts (user_id, name, type, exchange, is_default, is_active,
                                 is_paper_trading, paper_balances, created_at, updated_at)
            VALUES (?, 'Paper Trading Account', 'cex', 'coinbase', 1, 1, 1, ?, ?, ?)
        """, (user_id, initial_balances, datetime.utcnow(), datetime.utcnow()))

        conn.commit()
        print_success("Paper trading account created with $1000 USD and 0.01 BTC")
        return True

    except Exception as e:
        conn.rollback()
        print_error(f"Failed to create paper trading account: {e}")
        return False
    finally:
        conn.close()


def prompt_for_coinbase_credentials():
    """Prompt user for Coinbase CDP API credentials"""
    print()
    print_header("Coinbase Exchange Configuration")
    print()
    print_info("To trade on Coinbase, you need CDP (Coinbase Developer Platform) API credentials.")
    print_info("Get your API credentials at: https://portal.cdp.coinbase.com/projects")
    print()
    print_info("You need:")
    print("  1. API Key Name (looks like: organizations/.../apiKeys/...)")
    print("  2. Private Key (EC private key in PEM format)")
    print()

    if not prompt_yes_no("Configure Coinbase API credentials now?", default='yes'):
        print_info("You can configure Coinbase credentials later in Settings after login.")
        return None, None

    print()
    api_key_name = prompt_input("API Key Name (organizations/.../apiKeys/...)")

    print()
    print_info("For the private key, you can either:")
    print("  1. Paste the key directly (with \\n for newlines)")
    print("  2. Provide a file path to the .pem file")
    print()

    key_input = prompt_input("Private key or path to .pem file")

    # Check if it's a file path
    if key_input and not key_input.startswith('-----BEGIN'):
        key_path = Path(key_input).expanduser()
        if key_path.exists():
            try:
                with open(key_path, 'r') as f:
                    api_private_key = f.read().strip()
                print_success(f"Read private key from {key_path}")
            except Exception as e:
                print_error(f"Failed to read key file: {e}")
                return None, None
        else:
            # Could be raw base64 key or key with escaped newlines
            api_private_key = key_input.replace('\\n', '\n')
            # If it's just the raw base64 without PEM headers, wrap it
            if not api_private_key.startswith('-----BEGIN'):
                # Coinbase uses EC private keys
                api_private_key = f"-----BEGIN EC PRIVATE KEY-----\n{api_private_key}\n-----END EC PRIVATE KEY-----"
                print_info("Wrapped raw key in PEM format")
    else:
        # Direct key input with PEM headers
        api_private_key = key_input.replace('\\n', '\n') if key_input else None

    if not api_key_name or not api_private_key:
        print_warning("Incomplete credentials provided")
        return None, None

    return api_key_name, api_private_key


def parse_existing_env(env_path):
    """Parse existing .env file and return dict of key-value pairs"""
    if not env_path.exists():
        return {}

    env_vars = {}
    try:
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Parse key=value pairs
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    except Exception:
        pass
    return env_vars


def get_existing_jwt_secret(env_path):
    """Extract JWT_SECRET_KEY from existing .env file if it exists"""
    env_vars = parse_existing_env(env_path)
    return env_vars.get('JWT_SECRET_KEY')


def get_existing_encryption_key(env_path):
    """Extract ENCRYPTION_KEY from existing .env file if it exists"""
    env_vars = parse_existing_env(env_path)
    return env_vars.get('ENCRYPTION_KEY')


def generate_env_file(project_root, config):
    """Generate the .env file with provided configuration"""
    env_path = project_root / 'backend' / '.env'

    # Preserve existing JWT secret if .env exists, otherwise generate new one
    jwt_secret = get_existing_jwt_secret(env_path)
    if jwt_secret:
        print_info("Preserving existing JWT secret key")
    else:
        jwt_secret = secrets.token_urlsafe(32)
        print_info("Generated new JWT secret key")

    # Preserve existing encryption key if .env exists, otherwise generate new one
    encryption_key = get_existing_encryption_key(env_path)
    if encryption_key:
        print_info("Preserving existing encryption key")
    else:
        from cryptography.fernet import Fernet
        encryption_key = Fernet.generate_key().decode()
        print_info("Generated new encryption key for API credential storage")

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
# Encryption Key (for API credentials at rest)
# =============================================================================
ENCRYPTION_KEY={encryption_key}

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
    provider = config.get('system_ai_provider', 'gemini')
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
# Application Settings
# =============================================================================
DEBUG=false
LOG_LEVEL=INFO

# =============================================================================
# Exchange Credentials (stored per-user in database, not here)
# Users configure their Coinbase API credentials in the Settings page after login.
# =============================================================================
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


def create_db_cleanup_systemd(project_root, user):
    """Create systemd service and timer for daily database cleanup (Linux)"""
    services_dir = project_root / 'deployment'
    services_dir.mkdir(exist_ok=True)

    cleanup_service = f"""[Unit]
Description=Zenith Grid Database Cleanup
After=network.target

[Service]
Type=oneshot
User={user}
WorkingDirectory={project_root}/backend
ExecStart={project_root}/backend/venv/bin/python {project_root}/backend/maintenance/cleanup_database.py

[Install]
WantedBy=multi-user.target
"""

    cleanup_timer = """[Unit]
Description=Run Zenith Grid database cleanup daily at 3 AM

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
"""

    try:
        service_path = services_dir / 'zenith-db-cleanup.service'
        timer_path = services_dir / 'zenith-db-cleanup.timer'

        with open(service_path, 'w') as f:
            f.write(cleanup_service)

        with open(timer_path, 'w') as f:
            f.write(cleanup_timer)

        print_success("Database cleanup systemd files created in deployment/")
        print_info("To install, run:")
        print(f"  sudo cp {service_path} /etc/systemd/system/")
        print(f"  sudo cp {timer_path} /etc/systemd/system/")
        print("  sudo systemctl daemon-reload")
        print("  sudo systemctl enable zenith-db-cleanup.timer")
        print("  sudo systemctl start zenith-db-cleanup.timer")
        return True

    except Exception as e:
        print_error(f"Failed to create database cleanup systemd files: {e}")
        return False


def create_db_cleanup_launchd(project_root, user):
    """Create launchd plist for daily database cleanup (macOS)"""
    plist_dir = project_root / 'deployment'
    plist_dir.mkdir(exist_ok=True)

    # Run daily at 3 AM
    cleanup_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.zenithgrid.db-cleanup</string>
    <key>ProgramArguments</key>
    <array>
        <string>{project_root}/backend/venv/bin/python</string>
        <string>{project_root}/backend/maintenance/cleanup_database.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{project_root}/backend</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/zenith-db-cleanup.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/zenith-db-cleanup.error.log</string>
</dict>
</plist>
"""

    try:
        cleanup_path = plist_dir / 'com.zenithgrid.db-cleanup.plist'

        with open(cleanup_path, 'w') as f:
            f.write(cleanup_plist)

        print_success("Database cleanup launchd plist created in deployment/")
        print_info("To install, run:")
        print(f"  cp {cleanup_path} ~/Library/LaunchAgents/")
        print("  launchctl load ~/Library/LaunchAgents/com.zenithgrid.db-cleanup.plist")
        return True

    except Exception as e:
        print_error(f"Failed to create database cleanup launchd plist: {e}")
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
    # Check Python version FIRST - may re-execute with Python 3.11
    # This must happen before any user interaction to avoid double prompts
    if not check_python_version():
        return False

    print_header("Zenith Grid Setup Wizard")

    project_root = get_project_root()
    os_type = detect_os()
    current_user = os.getenv('USER', 'user')

    print(f"Project directory: {project_root}")
    print(f"Detected OS: {os_type.capitalize()}")
    print(f"Current user: {current_user}")
    print()

    # Check if this looks like a re-run (existing installation)
    db_path = project_root / 'backend' / 'trading.db'
    env_path = project_root / 'backend' / '.env'
    venv_path = project_root / 'backend' / 'venv'

    if db_path.exists() and env_path.exists() and venv_path.exists():
        print_warning("⚠️  Existing installation detected!")
        print()
        print_info("This appears to be an existing Zenith Grid installation.")
        print_info("Running setup again is safe and will:")
        print_info("  ✓ Preserve your database and existing data")
        print_info("  ✓ Preserve your JWT secret (sessions stay valid)")
        print_info("  ✓ Update dependencies if needed")
        print_info("  ✓ Skip steps that are already complete")
        print()
        print_info("If you just need to:")
        print_info("  • Update to latest version → Use: python3 update.py")
        print_info("  • Install/update services → Use: python3 setup.py --services-only")
        print_info("  • Start fresh → Use: python3 setup.py --cleanup (then re-run setup)")
        print()

        if not prompt_yes_no("Continue with setup anyway?", default='yes'):
            print_info("Setup cancelled. No changes made.")
            return False
        print()

    # Require license acceptance before proceeding
    if not display_license_and_get_acceptance(project_root):
        return False

    # Show what setup will do
    print_header("What This Setup Will Do")
    print()
    print("  This wizard will configure Zenith Grid for first-time use.")
    print("  The following steps will be performed:")
    print()
    print("  Prerequisites:")
    print("     - Python 3.10+ (required)")
    print("     - Node.js 18+ (required for frontend, https://nodejs.org/)")
    print()
    print("  1. Python Environment")
    print("     - Create a Python virtual environment (backend/venv)")
    print("     - Install Python dependencies from requirements.txt")
    print()
    print("  2. Frontend Dependencies")
    print("     - Install Node.js packages (npm install)")
    print("     - Skipped if Node.js not installed")
    print()
    print("  3. Database Initialization")
    print("     - Create SQLite database (backend/trading.db)")
    print("     - Set up required tables")
    print()
    print("  4. Environment Configuration")
    print("     - Generate .env file with JWT secrets")
    print("     - Optionally configure AI provider for coin categorization")
    print()
    print("  5. Admin User Creation")
    print("     - Create your initial admin account")
    print("     - Admins can create additional users via API")
    print()
    print("  6. System Services (Optional)")
    print("     - Install systemd/launchd services for auto-start")
    print()

    if not prompt_yes_no("Proceed with setup?", default='yes'):
        print()
        print_info("Setup cancelled.")
        return False

    print()

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

    # Check for git (needed for version display in frontend)
    if check_git_installed():
        print_success("Git is installed")
    else:
        print_warning("git not found. Version display in frontend will show 'dev'.")
        print_info("Install git for proper version display: https://git-scm.com/downloads")

    if check_npm_installed():
        # Auto-install if node_modules doesn't exist
        if not check_node_modules_exists(project_root):
            print_info("Frontend dependencies not found. Installing...")
            if not install_frontend_dependencies(project_root):
                print_warning("Frontend dependencies failed to install")
        else:
            print_success("Frontend dependencies already installed")
    else:
        print_warning("npm not found")

        # On macOS, offer to install via Homebrew
        if os_type == 'darwin':
            brew_path = get_brew_path()
            if brew_path:
                print()
                if prompt_yes_no("Install Node.js/npm via Homebrew?", default='yes'):
                    try:
                        result = run_with_spinner(
                            [brew_path, 'install', 'node'],
                            "Installing Node.js and npm (this may take a few minutes)",
                            success_msg="Node.js and npm installed!",
                            error_msg="Failed to install Node.js/npm"
                        )
                        if result.returncode == 0 and check_npm_installed():
                            print_success("npm is now available")
                            # Try to install frontend dependencies
                            if not check_node_modules_exists(project_root):
                                print_info("Installing frontend dependencies...")
                                install_frontend_dependencies(project_root)
                        else:
                            print_warning("npm installation may require restarting your terminal")
                            print_info("After restarting terminal, run: python3.11 setup.py")
                    except Exception as e:
                        print_error(f"Failed to install npm: {e}")
                        print_info("Try manually: brew install node")
                else:
                    print_info("To install manually: brew install node")
            else:
                print_warning(
                    "Homebrew not found. Install Homebrew first "
                    "to use automated installation."
                )
                brew_install_msg = (
                    'Install Homebrew: /bin/bash -c '
                    '"$(curl -fsSL https://raw.githubusercontent.com'
                    '/Homebrew/install/HEAD/install.sh)"'
                )
                print_info(brew_install_msg)
                print_info(
                    "Or download Node.js directly from: "
                    "https://nodejs.org/"
                )
        else:
            print_info("Please install Node.js to run the frontend.")
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

    # Parse existing .env values if file exists
    existing_env = parse_existing_env(env_path)

    config = {}

    if env_path.exists():
        print_warning(".env file already exists")
        if not prompt_yes_no("Review/update .env configuration?", default='no'):
            print_info("Keeping existing .env file")
        else:
            # Backup existing
            backup_path = env_path.with_suffix('.env.backup')
            shutil.copy(env_path, backup_path)
            print_success(f"Backed up existing .env to {backup_path}")

            print()
            print_header("System AI Configuration")
            print_info("IMPORTANT: System AI provides coin safety filtering for ALL bots.")
            print_info("The system analyzes all coins weekly and categorizes them as:")
            print_info("  - APPROVED, BORDERLINE, QUESTIONABLE, MEME, or BLACKLISTED")
            print_info("")
            print_info("WITHOUT coin categorization, bots will trade ANY coin including")
            print_info("scams, meme coins, and risky projects. This is a critical safety feature.")
            print_info("")
            print_info("This system-wide key is NOT used for user AI trading bots.")
            print_info("Each user must configure their own AI API keys in Settings")
            print_info("to use AI-powered trading strategies.")
            print_info("")
            print_info("STRONGLY RECOMMENDED: Configure at least one provider.")
            print()

            if prompt_yes_no("Configure a system AI provider for coin categorization?", default='yes'):
                config = prompt_for_ai_provider(config, existing_env)
            else:
                print_warning("Skipping system AI - coin categorization will not run.")
                print_warning("WARNING: Bots will be able to trade ALL coins without safety filtering!")

            generate_env_file(project_root, config)
    else:
        print()
        print_header("System AI Configuration")
        print_info("IMPORTANT: System AI provides coin safety filtering for ALL bots.")
        print_info("The system analyzes all coins weekly and categorizes them as:")
        print_info("  - APPROVED, BORDERLINE, QUESTIONABLE, MEME, or BLACKLISTED")
        print_info("")
        print_info("WITHOUT coin categorization, bots will trade ANY coin including")
        print_info("scams, meme coins, and risky projects. This is a critical safety feature.")
        print_info("")
        print_info("This system-wide key is NOT used for user AI trading bots.")
        print_info("Each user must configure their own AI API keys in Settings")
        print_info("to use AI-powered trading strategies.")
        print_info("")
        print_info("STRONGLY RECOMMENDED: Configure at least one provider.")
        print()

        if prompt_yes_no("Configure a system AI provider for coin categorization?", default='yes'):
            config = prompt_for_ai_provider(config, existing_env)
        else:
            print_warning("Skipping system AI - coin categorization will not run.")
            print_warning("WARNING: Bots will be able to trade ALL coins without safety filtering!")

        generate_env_file(project_root, config)

    # Step 5: Create Admin User
    print_step(5, "Create Admin User")

    # Check if any users exist and get existing admin
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    conn.close()

    existing_email, existing_display_name = get_existing_admin_user(project_root)

    create_user = False
    if user_count > 0:
        print_info(f"{user_count} user(s) already exist in database")
        if existing_email:
            display_suffix = (
                f" ({existing_display_name})"
                if existing_display_name else ""
            )
            print_info(f"Admin user: {existing_email}{display_suffix}")
        if prompt_yes_no("Create another admin user?", default='no'):
            create_user = True
        else:
            print_info("Skipping user creation")
    else:
        print_info("No users found. Creating initial admin user...")
        create_user = True

    user_id = None
    if create_user:
        print()
        # Offer existing email as default
        while True:
            if existing_email:
                email = prompt_input("Admin email address", default=existing_email)
            else:
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

        # Offer existing display name as default
        if existing_display_name:
            display_name = prompt_input("Display name (optional)", default=existing_display_name, required=False)
        else:
            display_name = prompt_input("Display name (optional)", required=False)

        # Need to ensure bcrypt is available
        sys.path.insert(0, str(project_root / 'backend'))
        user_id = create_admin_user(project_root, email, password, display_name or None)

        # Seed initial coin categorizations
        if user_id:
            seed_coin_categorizations(project_root, user_id)

        # Create default paper trading account
        if user_id:
            create_paper_trading_account(project_root, user_id)

        # Prompt for Coinbase credentials if user was created
        if user_id:
            api_key_name, api_private_key = prompt_for_coinbase_credentials()
            if api_key_name and api_private_key:
                create_coinbase_account(project_root, user_id, api_key_name, api_private_key)

    # Step 6: Service Installation
    print_step(6, "Service Installation (Optional)")

    if os_type == 'linux':
        print_info("Linux detected - can create systemd service files")
        if prompt_yes_no("Create systemd service files for auto-start?", default='no'):
            service_user = prompt_input("User to run services as", default=current_user)
            create_systemd_service(project_root, service_user)

        print()
        print_info("Database cleanup prevents log tables from bloating the database.")
        if prompt_yes_no("Create database cleanup timer (runs daily at 3 AM)?", default='yes'):
            service_user = prompt_input("User to run cleanup as", default=current_user)
            create_db_cleanup_systemd(project_root, service_user)

    elif os_type == 'mac':
        print_info("macOS detected - can create launchd plist files")
        if prompt_yes_no("Create launchd plist files for auto-start?", default='no'):
            create_launchd_plist(project_root, current_user)

        print()
        print_info("Database cleanup prevents log tables from bloating the database.")
        if prompt_yes_no("Create database cleanup job (runs daily at 3 AM)?", default='yes'):
            create_db_cleanup_launchd(project_root, current_user)

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

        # Database cleanup service
        print()
        print_info("Database cleanup prevents log tables from bloating the database.")
        install_db_cleanup = prompt_yes_no("Create database cleanup timer (runs daily at 3 AM)?", default='yes')
        if install_db_cleanup:
            create_db_cleanup_systemd(project_root, service_user)

        print()
        if prompt_yes_no("Install services now (requires sudo)?"):
            services_dir = project_root / 'deployment'
            backend_path = services_dir / 'zenith-backend.service'
            frontend_path = services_dir / 'zenith-frontend.service'

            print_info("Installing systemd services...")
            try:
                subprocess.run(['sudo', 'cp', str(backend_path), '/etc/systemd/system/'], check=True)
                subprocess.run(['sudo', 'cp', str(frontend_path), '/etc/systemd/system/'], check=True)

                # Install db cleanup if created
                if install_db_cleanup:
                    cleanup_service_path = services_dir / 'zenith-db-cleanup.service'
                    cleanup_timer_path = services_dir / 'zenith-db-cleanup.timer'
                    subprocess.run(['sudo', 'cp', str(cleanup_service_path), '/etc/systemd/system/'], check=True)
                    subprocess.run(['sudo', 'cp', str(cleanup_timer_path), '/etc/systemd/system/'], check=True)

                subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
                print_success("Service files installed")

                if prompt_yes_no("Enable services to start on boot?"):
                    subprocess.run(['sudo', 'systemctl', 'enable', 'zenith-backend', 'zenith-frontend'], check=True)
                    if install_db_cleanup:
                        subprocess.run(['sudo', 'systemctl', 'enable', 'zenith-db-cleanup.timer'], check=True)
                    print_success("Services enabled")

                if prompt_yes_no("Start services now?"):
                    subprocess.run(['sudo', 'systemctl', 'start', 'zenith-backend', 'zenith-frontend'], check=True)
                    if install_db_cleanup:
                        subprocess.run(['sudo', 'systemctl', 'start', 'zenith-db-cleanup.timer'], check=True)
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

        # Database cleanup service
        print()
        print_info("Database cleanup prevents log tables from bloating the database.")
        install_db_cleanup = prompt_yes_no("Create database cleanup job (runs daily at 3 AM)?", default='yes')
        if install_db_cleanup:
            create_db_cleanup_launchd(project_root, current_user)

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
                if install_db_cleanup:
                    cleanup_plist = plist_dir / 'com.zenithgrid.db-cleanup.plist'
                    shutil.copy(cleanup_plist, launch_agents_dir / 'com.zenithgrid.db-cleanup.plist')
                print_success("Plist files copied to ~/Library/LaunchAgents/")

                if prompt_yes_no("Load services now (start on boot)?"):
                    # Unload first if already loaded (ignore errors)
                    backend_plist_path = str(
                        launch_agents_dir / 'com.zenithgrid.backend.plist'
                    )
                    frontend_plist_path = str(
                        launch_agents_dir / 'com.zenithgrid.frontend.plist'
                    )
                    cleanup_plist_path = str(
                        launch_agents_dir / 'com.zenithgrid.db-cleanup.plist'
                    )
                    subprocess.run(
                        ['launchctl', 'unload', backend_plist_path],
                        capture_output=True
                    )
                    subprocess.run(
                        ['launchctl', 'unload', frontend_plist_path],
                        capture_output=True
                    )
                    if install_db_cleanup:
                        subprocess.run(
                            ['launchctl', 'unload', cleanup_plist_path],
                            capture_output=True
                        )

                    # Load services
                    subprocess.run(
                        ['launchctl', 'load', backend_plist_path],
                        check=True
                    )
                    subprocess.run(
                        ['launchctl', 'load', frontend_plist_path],
                        check=True
                    )
                    if install_db_cleanup:
                        subprocess.run(
                            ['launchctl', 'load', cleanup_plist_path],
                            check=True
                        )
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
                    if install_db_cleanup:
                        print("  tail -f /tmp/zenith-db-cleanup.log")

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
        cleanup_service = Path('/etc/systemd/system/zenith-db-cleanup.service')
        cleanup_timer = Path('/etc/systemd/system/zenith-db-cleanup.timer')

        # Check if services exist
        backend_exists = backend_service.exists()
        frontend_exists = frontend_service.exists()
        cleanup_service_exists = cleanup_service.exists()
        cleanup_timer_exists = cleanup_timer.exists()

        if not backend_exists and not frontend_exists and not cleanup_timer_exists:
            print_warning("No Zenith Grid services found installed")
            return True

        try:
            # Stop services first
            print_info("Stopping services...")
            subprocess.run(['sudo', 'systemctl', 'stop', 'zenith-backend'], capture_output=True)
            subprocess.run(['sudo', 'systemctl', 'stop', 'zenith-frontend'], capture_output=True)
            subprocess.run(['sudo', 'systemctl', 'stop', 'zenith-db-cleanup.timer'], capture_output=True)
            print_success("Services stopped")

            # Disable services
            print_info("Disabling services...")
            subprocess.run(['sudo', 'systemctl', 'disable', 'zenith-backend'], capture_output=True)
            subprocess.run(['sudo', 'systemctl', 'disable', 'zenith-frontend'], capture_output=True)
            subprocess.run(['sudo', 'systemctl', 'disable', 'zenith-db-cleanup.timer'], capture_output=True)
            print_success("Services disabled")

            # Remove service files
            print_info("Removing service files...")
            if backend_exists:
                subprocess.run(['sudo', 'rm', str(backend_service)], check=True)
                print_success(f"Removed {backend_service}")
            if frontend_exists:
                subprocess.run(['sudo', 'rm', str(frontend_service)], check=True)
                print_success(f"Removed {frontend_service}")
            if cleanup_service_exists:
                subprocess.run(['sudo', 'rm', str(cleanup_service)], check=True)
                print_success(f"Removed {cleanup_service}")
            if cleanup_timer_exists:
                subprocess.run(['sudo', 'rm', str(cleanup_timer)], check=True)
                print_success(f"Removed {cleanup_timer}")

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
        cleanup_plist = launch_agents_dir / 'com.zenithgrid.db-cleanup.plist'

        # Check if services exist
        backend_exists = backend_plist.exists()
        frontend_exists = frontend_plist.exists()
        cleanup_exists = cleanup_plist.exists()

        if not backend_exists and not frontend_exists and not cleanup_exists:
            print_warning("No Zenith Grid services found installed")
            return True

        try:
            # Unload services first (stop them)
            print_info("Unloading services...")
            if backend_exists:
                subprocess.run(['launchctl', 'unload', str(backend_plist)], capture_output=True)
            if frontend_exists:
                subprocess.run(['launchctl', 'unload', str(frontend_plist)], capture_output=True)
            if cleanup_exists:
                subprocess.run(['launchctl', 'unload', str(cleanup_plist)], capture_output=True)
            print_success("Services unloaded (stopped)")

            # Remove plist files
            print_info("Removing plist files...")
            if backend_exists:
                backend_plist.unlink()
                print_success(f"Removed {backend_plist}")
            if frontend_exists:
                frontend_plist.unlink()
                print_success(f"Removed {frontend_plist}")
            if cleanup_exists:
                cleanup_plist.unlink()
                print_success(f"Removed {cleanup_plist}")

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

    # Clean Vite cache (can cause "Outdated Optimize Dep" errors)
    vite_cache = project_root / 'frontend' / 'node_modules' / '.vite'
    if vite_cache.exists():
        print_info("Removing Vite cache...")
        try:
            shutil.rmtree(vite_cache)
            print_success(f"Removed {vite_cache}")
        except Exception as e:
            print_error(f"Failed to remove Vite cache: {e}")

    # Clean Python cache files
    pycache_count = 0
    for pycache in project_root.rglob('__pycache__'):
        try:
            shutil.rmtree(pycache)
            pycache_count += 1
        except Exception:
            pass
    if pycache_count > 0:
        print_success(f"Removed {pycache_count} __pycache__ directories")

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
