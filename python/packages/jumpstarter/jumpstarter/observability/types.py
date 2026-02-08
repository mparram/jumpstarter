"""
Types and constants for the observability module.
"""

from pydantic import BaseModel, Field


class ObservabilityConfigV1Alpha1(BaseModel):
    """Configuration for the observability module."""

    # Metrics server
    metrics_enabled: bool = Field(default=False, description="Enable or disable the metrics server")
    metrics_port: int = Field(default=9090, description="Port where the metrics endpoint will be exposed")
    metrics_host: str = Field(default="0.0.0.0", description="Host where the metrics endpoint will be exposed")

    # OTLP server
    otlp_enabled: bool = Field(default=False, description="Enable or disable the OTLP gRPC server")
    otlp_port: int = Field(default=4317, description="Port where the OTLP gRPC server will listen")
    otlp_host: str = Field(default="0.0.0.0", description="Host where the OTLP gRPC server will listen")

