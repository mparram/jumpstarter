"""
OTLP (OpenTelemetry Protocol) module for Jumpstarter exporters.

This module provides functionality to receive telemetry signals (metrics, logs, traces)
from otel-collector via OTLP-gRPC and forward them to the controller.
"""

from jumpstarter.observability.otlp.controller_client import ObservabilityControllerClient
from jumpstarter.observability.otlp.server import OTLPServer

__all__ = ["OTLPServer", "ObservabilityControllerClient"]

