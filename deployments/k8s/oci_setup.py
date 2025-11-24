#!/usr/bin/env python3
"""
OCI Container Registry Setup Helper
This script helps you set up authentication with OCI Container Registry
"""

import os
import shutil
import sys
import subprocess
import getpass
from pathlib import Path

# Colors for output
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"  # No Color


def print_colored(message: str, color: str = NC) -> None:
    """Print a colored message."""
    print(f"{color}{message}{NC}")


def check_command(cmd: str) -> bool:
    """Check if a command is available."""
    return shutil.which(cmd) is not None


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    result = subprocess.run(cmd, check=check)
    return result


def append_to_bashrc(line: str) -> None:
    """Append a line to ~/.bashrc."""
    bashrc_path = Path.home() / ".bashrc"
    with bashrc_path.open("a") as f:
        f.write(f"{line}\n")


def main() -> None:
    """Main function."""
    print_colored("🔐 OCI Container Registry Setup", BLUE)
    print()

    # Check for container runtime (prefer Podman over Docker)
    container_cmd = None
    if check_command("podman"):
        container_cmd = "podman"
        print_colored("✅ Using Podman", GREEN)
    elif check_command("docker"):
        container_cmd = "docker"
        print_colored("⚠️  Using Docker (Podman preferred)", YELLOW)
    else:
        print_colored("❌ Neither Podman nor Docker is installed or in PATH", RED)
        print("Please install Podman (preferred) or Docker")
        sys.exit(1)

    print_colored("📋 Prerequisites:", YELLOW)
    print("1. OCI Console access")
    print("2. Your OCI namespace (found in Object Storage > Namespaces)")
    print("3. An Auth Token (create in Identity > Users > Your User > Auth Tokens)")
    print()

    # Get OCI namespace
    oci_namespace = input("Enter your OCI namespace (e.g., your-tenant-name): ").strip()
    if not oci_namespace:
        print_colored("❌ OCI namespace is required", RED)
        sys.exit(1)

    # Get OCI region
    oci_region_input = input("Enter your OCI region (default: us-chicago-1): ").strip()
    oci_region = oci_region_input if oci_region_input else "us-chicago-1"

    # Get OCI username (non-federated format)
    oci_username = input("Enter your OCI username (e.g., felipe.f.garcia@oracle.com): ").strip()
    if not oci_username:
        print_colored("❌ OCI username is required", RED)
        sys.exit(1)
    print_colored("✅ Using non-federated login format", GREEN)

    # Get Auth Token
    print_colored("🔑 Enter your OCI Auth Token (it won't be displayed):", YELLOW)
    auth_token = getpass.getpass("")
    if not auth_token:
        print_colored("❌ Auth Token is required", RED)
        sys.exit(1)

    print()

    # Set environment variables
    os.environ["OCI_NAMESPACE"] = oci_namespace
    os.environ["OCI_REGION"] = oci_region

    print_colored("🔧 Setting environment variables...", YELLOW)
    append_to_bashrc(f'export OCI_NAMESPACE="{oci_namespace}"')
    append_to_bashrc(f'export OCI_REGION="{oci_region}"')

    # Login to OCI Container Registry
    print_colored("🔐 Logging into OCI Container Registry...", YELLOW)
    registry_url = f"{oci_region}.ocir.io"
    login_cmd = [
        container_cmd,
        "login",
        registry_url,
        "-u",
        f"{oci_namespace}/{oci_username}",
        "-p",
        auth_token,
    ]

    try:
        run_command(login_cmd)
        print_colored("✅ Successfully logged into OCI Container Registry", GREEN)
        print()
        print_colored("📝 Environment variables set:", BLUE)
        print(f"  OCI_NAMESPACE={oci_namespace}")
        print(f"  OCI_REGION={oci_region}")
        print()
        print_colored("🎉 Setup complete! You can now build and push images.", GREEN)
        print()
        print_colored("💡 Next steps:", YELLOW)
        print("1. Run: ./build_and_push.py --push")
        print("2. Update 06-aegra-app.yaml with your image URL")
        print("3. Run: ./deploy.py")
    except subprocess.CalledProcessError:
        print_colored("❌ Failed to login to OCI Container Registry", RED)
        print("Please check your credentials and try again")
        sys.exit(1)


if __name__ == "__main__":
    main()

