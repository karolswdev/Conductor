"""
Configuration management for Conductor.
"""

import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class MCPConfig(BaseModel):
    """MCP server configuration."""

    server_url: str = Field(default="stdio://playwright-mcp")
    timeout: float = Field(default=30.0, ge=1.0)
    max_retries: int = Field(default=3, ge=1, le=10)


class AuthConfig(BaseModel):
    """Authentication configuration."""

    timeout: int = Field(default=300, ge=30, le=600, description="Time allowed for manual login (seconds)")
    check_interval: float = Field(default=2.0, ge=0.5)
    headless: bool = Field(default=False)


class RetryConfig(BaseModel):
    """Default retry configuration."""

    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_delay: float = Field(default=5.0, ge=1.0)
    backoff_factor: float = Field(default=2.0, ge=1.0)
    max_delay: float = Field(default=300.0, ge=10.0)
    jitter: float = Field(default=0.2, ge=0.0, le=0.5)


class UIConfig(BaseModel):
    """UI configuration."""

    theme: str = Field(default="default")
    refresh_rate: int = Field(default=10, ge=1, le=60)
    show_splash: bool = Field(default=True)
    splash_duration: float = Field(default=2.0, ge=0.0)


class ExecutionConfig(BaseModel):
    """Task execution configuration."""

    max_parallel_tasks: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Maximum number of tasks to run in parallel (1-10)",
    )
    parallel_mode: bool = Field(
        default=False, description="Enable parallel task execution"
    )


class Config(BaseModel):
    """Main configuration for Conductor."""

    mcp: MCPConfig = Field(default_factory=MCPConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    default_repository: Optional[str] = Field(default=None)

    @classmethod
    def from_file(cls, path: Path) -> "Config":
        """
        Load configuration from a YAML file.

        Args:
            path: Path to config file

        Returns:
            Config instance
        """
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls(**data)

    def to_file(self, path: Path) -> None:
        """
        Save configuration to a YAML file.

        Args:
            path: Path to save config
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)


def load_config(config_path: Optional[Path] = None) -> Config:
    """
    Load configuration from file or use defaults.

    Args:
        config_path: Path to config file. If None, uses ~/.conductor/config.yaml

    Returns:
        Config instance
    """
    if config_path is None:
        config_path = Path.home() / ".conductor" / "config.yaml"

    if config_path.exists():
        return Config.from_file(config_path)

    # Return default config
    return Config()
