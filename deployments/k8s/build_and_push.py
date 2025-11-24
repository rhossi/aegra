#!/usr/bin/env python3
"""
Aegra Docker Build and Push Script

This script builds the Aegra Docker image and pushes it to a registry using the
Docker Python SDK. It supports both Docker and Podman (preferred) container
runtimes.

The script:
1. Detects and connects to Docker or Podman daemon
2. Builds the image for linux/amd64 platform (Kubernetes compatibility)
3. Optionally pushes the image to OCI Container Registry

Usage:
    ./build_and_push.py          # Build only
    ./build_and_push.py --push    # Build and push to registry
    ./build_and_push.py -p        # Short form for push
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import docker
except ImportError:
    print("❌ docker Python SDK not installed. Install it with: "
          "uv pip install docker")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
except ImportError:
    print("❌ rich library not installed. Install it with: "
          "uv pip install rich")
    sys.exit(1)

# Initialize Rich console
console = Console()

# Constants
DEFAULT_TAG = "latest"
DEFAULT_REGION = "us-chicago-1"
PLATFORM = "linux/amd64"
PODMAN_SOCKET = Path("/run/podman/podman.sock")
PODMAN_ROOTLESS_SOCKET = (
    Path.home() / ".local/share/containers/podman/machine/"
    "podman-machine-default/podman.sock"
)


@dataclass
class BuildConfig:
    """Configuration for building and pushing Docker images."""

    image_name: str
    tag: str
    oci_region: str
    oci_namespace: str
    oci_registry: str
    local_image: str

    @property
    def full_image_name(self) -> str:
        """Get full image name for display purposes."""
        return f"{self.image_name}:{self.tag}"

    @property
    def oci_image_name(self) -> str:
        """Get full OCI registry image name."""
        return (
            f"{self.oci_registry}/{self.oci_namespace}/"
            f"{self.image_name}:{self.tag}"
        )


def get_docker_client() -> tuple[docker.DockerClient | None, str | None]:
    """Get Docker client, preferring Podman socket if available.

    This function attempts to connect to container runtimes in order of
    preference:
    1. Podman system socket (/run/podman/podman.sock) - preferred
    2. Docker default socket (from environment)
    3. Podman rootless socket (for user-level Podman)

    The Docker Python SDK works with both Docker and Podman since Podman
    exposes a Docker-compatible API socket.

    Returns:
        Tuple of (DockerClient, runtime_type) or (None, None) if no runtime
        found. runtime_type is either "podman" or "docker".
    """
    # Try Podman system socket first (preferred runtime)
    if PODMAN_SOCKET.exists():
        client = _try_connect_socket(str(PODMAN_SOCKET), "podman")
        if client:
            return client, "podman"

    # Try default Docker socket
    try:
        client = docker.from_env()
        client.ping()  # Verify connection works
        return client, "docker"
    except (docker.errors.DockerException, Exception):
        pass

    # Try Podman rootless socket (for user-level Podman installations)
    if PODMAN_ROOTLESS_SOCKET.exists():
        client = _try_connect_socket(
            str(PODMAN_ROOTLESS_SOCKET), "podman"
        )
        if client:
            return client, "podman"

    # No container runtime found
    return None, None


def _try_connect_socket(
    socket_path: str, _runtime_type: str
) -> docker.DockerClient | None:
    """Try to connect to a container runtime socket.

    Args:
        socket_path: Path to the socket file
        _runtime_type: Type of runtime ("podman" or "docker") - unused

    Returns:
        DockerClient if connection successful, None otherwise
    """
    try:
        client = docker.DockerClient(base_url=f"unix://{socket_path}")
        client.ping()  # Verify connection works
        return client
    except (docker.errors.DockerException, Exception):
        return None


def load_config() -> BuildConfig:
    """Load configuration from environment variables.

    Returns:
        BuildConfig instance with loaded configuration
    """
    image_name = "aegra"
    tag = os.environ.get("AEGRA_TAG", DEFAULT_TAG)
    oci_region = os.environ.get("OCI_REGION", DEFAULT_REGION)
    oci_namespace = os.environ.get("OCI_NAMESPACE", "")
    oci_registry = os.environ.get(
        "OCI_REGISTRY", f"{oci_region}.ocir.io"
    )
    local_image = "localhost/aegra"

    return BuildConfig(
        image_name=image_name,
        tag=tag,
        oci_region=oci_region,
        oci_namespace=oci_namespace,
        oci_registry=oci_registry,
        local_image=local_image,
    )


def print_build_logs(logs, progress: Progress | None = None) -> None:
    """Print build logs in real-time.

    Args:
        logs: Generator of build log dictionaries
        progress: Optional Rich Progress instance for status updates
    """
    task_id = None
    if progress:
        task_id = progress.add_task(
            "[cyan]Building...", total=None
        )

    for log in logs:
        if "stream" in log:
            # Normal build output (layer creation, step completion, etc.)
            stream = log["stream"].strip()
            if stream:
                # Extract useful information from stream
                if (
                    "Step" in stream
                    and "/" in stream
                    and progress
                    and task_id is not None
                ):
                    progress.update(
                        task_id,
                        description=f"[cyan]{stream[:60]}...",
                    )
                console.print(stream, style="dim")
        elif "error" in log:
            # Build error occurred
            console.print(f"[red]Error: {log['error']}[/red]")
        elif progress and task_id is not None:
            progress.update(task_id, advance=1)


def handle_build_error(error: docker.errors.BuildError) -> None:
    """Handle Docker build errors.

    Args:
        error: The BuildError exception that was raised
    """
    console.print("\n[bold red]❌ Failed to build image[/bold red]")
    console.print("[yellow]Build errors:[/yellow]")
    print_build_logs(error.build_log)
    sys.exit(1)


def build_image(
    client: docker.DockerClient, config: BuildConfig
) -> docker.models.images.Image:
    """Build the Docker image.

    Args:
        client: Docker client instance
        config: Build configuration

    Returns:
        Built Docker image object

    Raises:
        SystemExit: If build fails
    """
    # Get the project root directory (parent of deployments/k8s)
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent.parent

    # Change to project root directory - Docker build context needs to be
    # at the project root to access all necessary files
    os.chdir(project_root)

    # Path to the Dockerfile relative to project root
    dockerfile_path = project_root / "deployments" / "docker" / "Dockerfile"

    try:
        console.print(
            "\n[bold yellow]📦 Building image (this may take a while)...[/bold yellow]"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            image, build_logs = client.images.build(
                path=str(project_root),
                dockerfile=str(dockerfile_path.relative_to(project_root)),
                tag=config.local_image,
                platform=PLATFORM,
                rm=True,
            )

            # Print build logs in real-time
            print_build_logs(build_logs, progress)

        console.print(
            f"\n[bold green]✅ Image built successfully for {PLATFORM}[/bold green]"
        )
        return image
    except docker.errors.BuildError as e:
        handle_build_error(e)
    except Exception as e:
        console.print(f"\n[bold red]❌ Failed to build image: {e}[/bold red]")
        sys.exit(1)


def validate_push_config(config: BuildConfig) -> None:
    """Validate that configuration is sufficient for pushing.

    Args:
        config: Build configuration

    Raises:
        SystemExit: If OCI_NAMESPACE is not set
    """
    if not config.oci_namespace:
        console.print(
            Panel(
                "[bold red]❌ OCI_NAMESPACE environment variable is not set[/bold red]\n\n"
                "Set it to your OCI namespace "
                "(e.g., export OCI_NAMESPACE=your-namespace)\n\n"
                "You can find your namespace in the OCI Console under "
                "'Administration' > 'Tenancy Details'",
                title="[yellow]Configuration Error[/yellow]",
                border_style="red",
            )
        )
        console.print("\n[bold yellow]📋 Prerequisites:[/bold yellow]")
        console.print("1. Create a Container Registry repository in OCI Console:")
        console.print(
            "   [cyan]Developer Services → Containers & Artifacts → "
            "Container Registry[/cyan]"
        )
        console.print("2. Get your Object Storage Namespace from Tenancy Details")
        console.print("3. Set OCI_NAMESPACE environment variable")
        sys.exit(1)


def process_push_logs(push_logs, progress: Progress | None = None) -> None:
    """Process push logs and detect errors.

    Args:
        push_logs: Generator of push log dictionaries
        progress: Optional Rich Progress instance for status updates

    Raises:
        Exception: If an error is detected in the push logs
    """
    error_occurred = False
    error_message = ""
    task_id = None

    if progress:
        task_id = progress.add_task(
            "[cyan]Pushing layers...", total=None
        )

    for log in push_logs:
        if "status" in log:
            status = log.get("status", "")
            if any(
                keyword in status
                for keyword in ("Pushing", "Pushed", "Layer")
            ):
                # Show progress for layer operations
                if (
                    ("Pushed" in status or "Pushing" in status)
                    and progress
                    and task_id is not None
                ):
                    progress.update(
                        task_id,
                        description=f"[cyan]{status[:50]}...",
                    )
                console.print(f"  [dim]{status}[/dim]")
            elif "error" in log:
                error_occurred = True
                error_message = log.get("error", "Unknown error")
                console.print(f"  [red]Error: {error_message}[/red]")
        elif "errorDetail" in log:
            error_occurred = True
            error_detail = log.get("errorDetail", {})
            error_message = error_detail.get("message", "Unknown error")
            console.print(f"  [red]Error: {error_message}[/red]")

    if error_occurred:
        raise Exception(f"Push failed: {error_message}")


def print_auth_troubleshooting(runtime_type: str, oci_registry: str) -> None:
    """Print authentication troubleshooting steps.

    Args:
        runtime_type: Container runtime type ("podman" or "docker")
        oci_registry: OCI registry URL
    """
    troubleshooting_steps = Table(
        title="[yellow]💡 Troubleshooting Steps[/yellow]",
        show_header=False,
        box=None,
        padding=(0, 1),
    )
    troubleshooting_steps.add_column(style="cyan")
    troubleshooting_steps.add_column()

    troubleshooting_steps.add_row(
        "1.",
        "Verify you're logged in to OCI Container Registry:",
    )
    troubleshooting_steps.add_row(
        "",
        f"[bold]{runtime_type} login {oci_registry}[/bold]",
    )
    troubleshooting_steps.add_row("", "")
    troubleshooting_steps.add_row(
        "2.",
        "Or run the setup script to configure authentication:",
    )
    troubleshooting_steps.add_row("", "[bold]./oci_setup.py[/bold]")
    troubleshooting_steps.add_row("", "")
    troubleshooting_steps.add_row("3.", "Verify your credentials:")
    troubleshooting_steps.add_row(
        "",
        "  • OCI_NAMESPACE should be set correctly",
    )
    troubleshooting_steps.add_row(
        "",
        "  • Your auth token may have expired",
    )
    troubleshooting_steps.add_row(
        "",
        "  • Check OCI Console: Identity > Users > Your User > "
        "Auth Tokens",
    )
    troubleshooting_steps.add_row("", "")
    troubleshooting_steps.add_row("4.", "For Podman, check stored credentials:")
    if runtime_type == "podman":
        troubleshooting_steps.add_row(
            "",
            "[bold]podman login --get-login us-chicago-1.ocir.io[/bold]",
        )
    else:
        troubleshooting_steps.add_row(
            "",
            "[bold]cat ~/.docker/config.json[/bold]",
        )

    console.print(
        Panel(
            "[bold yellow]🔐 Authentication Error Detected[/bold yellow]\n\n"
            "The 403 Forbidden error indicates an authentication problem.",
            title="[red]Authentication Error[/red]",
            border_style="red",
        )
    )
    console.print()
    console.print(troubleshooting_steps)


def push_image(
    client: docker.DockerClient,
    image: docker.models.images.Image,
    config: BuildConfig,
    runtime_type: str,
) -> None:
    """Push the Docker image to OCI Container Registry.

    Args:
        client: Docker client instance
        image: Docker image object to push
        config: Build configuration
        runtime_type: Container runtime type

    Raises:
        SystemExit: If push fails
    """
    validate_push_config(config)

    oci_image_name = config.oci_image_name

    # Debug output for push using Rich table
    debug_table = Table(
        title="[blue]🔍 Push Debug Information[/blue]",
        show_header=False,
        box=None,
        padding=(0, 1),
    )
    debug_table.add_column(style="cyan", width=20)
    debug_table.add_column()

    debug_table.add_row("OCI Registry:", config.oci_registry)
    debug_table.add_row("OCI Namespace:", config.oci_namespace)
    debug_table.add_row("Image Name:", config.image_name)
    debug_table.add_row("Tag:", config.tag)
    debug_table.add_row("OCI Image Name:", f"[bold]{oci_image_name}[/bold]")

    console.print()
    console.print(debug_table)
    console.print()

    try:
        # Tag the local image for the registry
        console.print("[bold yellow]🏷️  Tagging image...[/bold yellow]")
        image.tag(oci_image_name)

        # Push the image to OCI Container Registry
        console.print(
            "[bold yellow]📤 Pushing image to OCI Container Registry...[/bold yellow]"
        )
        console.print(
            "[dim]This may take a while depending on image size and "
            "network speed...[/dim]\n"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            push_logs = client.images.push(
                oci_image_name,
                stream=True,  # Stream logs in real-time
                decode=True,  # Decode JSON logs to dictionaries
            )

            process_push_logs(push_logs, progress)

        console.print(
            "\n[bold green]✅ Image pushed successfully to OCI Container Registry[/bold green]"
        )
        console.print(
            f"[bold blue]📝 Update your Kubernetes manifests to use: "
            f"{config.oci_image_name}"
        )
    except docker.errors.APIError as e:
        console.print("\n[bold red]❌ Failed to push image[/bold red]")
        console.print()

        error_msg = str(e)
        if any(
            keyword in error_msg.lower()
            for keyword in ("403", "forbidden", "unauthorized")
        ):
            print_auth_troubleshooting(runtime_type, config.oci_registry)
        else:
            console.print("[yellow]Error details:[/yellow]")
            console.print(Panel(error_msg, border_style="red"))
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]❌ Failed to push image: {e}[/bold red]")
        sys.exit(1)


def print_push_instructions(_config: BuildConfig) -> None:
    """Print instructions for pushing the image.

    Args:
        _config: Build configuration - unused
    """
    script_name = Path(__file__).name

    instructions = Table(
        title="[yellow]💡 Push Instructions[/yellow]",
        show_header=False,
        box=None,
        padding=(0, 1),
    )
    instructions.add_column(style="cyan")
    instructions.add_column()

    instructions.add_row(
        "To push:",
        f"[bold]{script_name} --push[/bold]",
    )
    instructions.add_row("", "")
    instructions.add_row("Set environment variables:", "")
    instructions.add_row(
        "",
        "[bold]export OCI_NAMESPACE=your-namespace[/bold]",
    )
    instructions.add_row(
        "",
        "[bold]export OCI_REGION=your-region[/bold] "
        "[dim](optional, defaults to us-chicago-1)[/dim]",
    )

    console.print()
    console.print(instructions)


def main() -> None:
    """Main function that orchestrates the build and push process."""
    # Load configuration
    config = load_config()

    console.print(
        Panel(
            "[bold blue]🐳 Building Aegra Docker image...[/bold blue]",
            border_style="blue",
        )
    )

    # Connect to Container Runtime (Docker or Podman)
    client, runtime_type = get_docker_client()
    if client is None:
        console.print(
            Panel(
                "[bold red]❌ Cannot connect to Docker or Podman daemon[/bold red]\n\n"
                "Please ensure Docker or Podman is running\n\n"
                "[yellow]For Docker:[/yellow]\n"
                "  • Start Docker daemon\n\n"
                "[yellow]For Podman:[/yellow]\n"
                "  • Start Podman service: "
                "[bold]systemctl --user start podman.socket[/bold]\n"
                "  • Or use rootless: [bold]podman machine start[/bold]",
                title="[red]Connection Error[/red]",
                border_style="red",
            )
        )
        sys.exit(1)

    # Inform user which runtime is being used
    if runtime_type == "podman":
        console.print("[bold green]✅ Using Podman[/bold green]")
    else:
        console.print(
            "[bold yellow]⚠️  Using Docker (Podman preferred)[/bold yellow]"
        )

    console.print(
        f"[bold yellow]🔨 Using existing local image: {config.local_image}[/bold yellow]"
    )

    # Debug output using Rich table
    debug_table = Table(
        title="[blue]🔍 Debug Information[/blue]",
        show_header=False,
        box=None,
        padding=(0, 1),
    )
    debug_table.add_column(style="cyan", width=20)
    debug_table.add_column()

    debug_table.add_row("Runtime:", runtime_type)
    debug_table.add_row("Local image:", config.local_image)
    debug_table.add_row("Full image name:", config.full_image_name)

    console.print()
    console.print(debug_table)
    console.print()

    # Build image
    console.print(
        f"[bold yellow]🔨 Building image for {PLATFORM} architecture...[/bold yellow]"
    )
    image = build_image(client, config)

    # Check if user wants to push
    should_push = "--push" in sys.argv or "-p" in sys.argv

    if should_push:
        push_image(client, image, config, runtime_type)
    else:
        print_push_instructions(config)

    console.print(
        "\n[bold green]🎉 Build completed![/bold green]"
    )


if __name__ == "__main__":
    main()
