"""
Types and constants for the metrics module.
"""

from pydantic import BaseModel, Field


class MetricsConfigV1Alpha1(BaseModel):
    """Configuration for the metrics module."""

    enabled: bool = Field(default=False, description="Enable or disable the metrics server")
    port: int = Field(default=9090, description="Port where the metrics endpoint will be exposed")
    host: str = Field(default="0.0.0.0", description="Host where the metrics endpoint will be exposed")

