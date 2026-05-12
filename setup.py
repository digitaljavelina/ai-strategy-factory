#!/usr/bin/env python3
"""
Setup script for AI Strategy Factory.

This script helps set up the project on any platform.
Run: python setup.py
"""

import os
import platform
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"\n{description}...")
    try:
        subprocess.run(cmd, check=True, shell=True)
        print(f"  Done!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Error: {e}")
        return False


def main():
    print("=" * 60)
    print("AI Strategy Factory - Setup")
    print("=" * 60)
    print(f"\nPlatform: {platform.system()} ({platform.machine()})")
    print(f"Python: {sys.version}")

    project_dir = Path(__file__).parent.absolute()
    os.chdir(project_dir)

    # Check Python version
    if sys.version_info < (3, 9):
        print("\nError: Python 3.9 or higher is required")
        print(f"Current version: {sys.version}")
        sys.exit(1)

    # Create virtual environment
    venv_dir = project_dir / "venv"
    if not venv_dir.exists():
        run_command("uv venv venv", "Creating virtual environment")
    else:
        print("\nVirtual environment already exists")

    # Determine activation command
    if platform.system() == "Windows":
        activate_cmd = ".\\venv\\Scripts\\activate"
    else:
        activate_cmd = "source venv/bin/activate"

    # Install dependencies
    run_command("uv pip install -r requirements.txt", "Installing dependencies")

    # Create .env file if it doesn't exist
    env_file = project_dir / ".env"
    env_example = project_dir / ".env.example"

    if not env_file.exists() and env_example.exists():
        print("\n Creating .env file from template...")
        env_file.write_text(env_example.read_text())
        print("  Done! Please edit .env with your API keys")
    elif not env_file.exists():
        print("\n Creating .env file...")
        env_content = """# AI Strategy Factory - Environment Variables
PERPLEXITY_API_KEY=your-api-key-here
GEMINI_API_KEY=your-api-key-here
"""
        env_file.write_text(env_content)
        print("  Done! Please edit .env with your API keys")

    # Print success message
    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)

    print("\nNext steps:")
    print(f"  1. Edit .env with your API keys:")
    print(f"     - Get Perplexity API key: https://www.perplexity.ai/settings/api")
    print(f"     - Get Gemini API key: https://aistudio.google.com/apikey")
    print(f"\n  2. Activate the virtual environment:")
    print(f"     {activate_cmd}")
    print(f"\n  3. Run the web app:")
    print(f"     python -m strategy_factory.webapp")
    print(f"\n  4. Open http://localhost:8888 in your browser")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
