"""
gRPC client for forwarding telemetry signals to the controller.

This client forwards metrics, logs, and traces received from otel-collector
to the controller using OpenTelemetry's standard OTLP services.
"""

import logging
from typing import Callable, Optional

import grpc

# OpenTelemetry proto imports
try:
    from jumpstarter_protocol.opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2_grpc
    from jumpstarter_protocol.opentelemetry.proto.collector.logs.v1 import logs_service_pb2_grpc
    from jumpstarter_protocol.opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc
    OTLP_AVAILABLE = True
except ImportError:
    OTLP_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(
        "OpenTelemetry protos not available. Controller client will not function. "
        "Run 'make protobuf-gen' to generate protos."
    )

logger = logging.getLogger(__name__)


class ObservabilityControllerClient:
    """gRPC client for forwarding telemetry signals to the controller."""

    def __init__(self, channel_factory: Callable[[], grpc.aio.Channel]):
        """
        Initialize the observability controller client.

        Args:
            channel_factory: Async callable that returns a gRPC channel to the controller
        """
        if not OTLP_AVAILABLE:
            raise ImportError(
                "OpenTelemetry protos are not available. "
                "Please run 'make protobuf-gen' to generate them."
            )
        self.channel_factory = channel_factory
        self._channel: Optional[grpc.aio.Channel] = None
        self._metrics_stub: Optional[metrics_service_pb2_grpc.MetricsServiceStub] = None
        self._logs_stub: Optional[logs_service_pb2_grpc.LogsServiceStub] = None
        self._traces_stub: Optional[trace_service_pb2_grpc.TraceServiceStub] = None

    async def _ensure_connected(self):
        """Ensure we have an active connection to the controller."""
        if self._channel is None:
            self._channel = await self.channel_factory()
            self._metrics_stub = metrics_service_pb2_grpc.MetricsServiceClient(self._channel)
            self._logs_stub = logs_service_pb2_grpc.LogsServiceClient(self._channel)
            self._traces_stub = trace_service_pb2_grpc.TraceServiceClient(self._channel)

    async def export_metrics(self, request):
        """
        Forward metrics to the controller.

        Args:
            request: ExportMetricsServiceRequest from OpenTelemetry

        Returns:
            ExportMetricsServiceResponse from the controller
        """
        try:
            await self._ensure_connected()
            return await self._metrics_stub.Export(request)
        except Exception as e:
            logger.error("Error forwarding metrics to controller: %s", e, exc_info=True)
            raise

    async def export_logs(self, request):
        """
        Forward logs to the controller.

        Args:
            request: ExportLogsServiceRequest from OpenTelemetry

        Returns:
            ExportLogsServiceResponse from the controller
        """
        try:
            await self._ensure_connected()
            return await self._logs_stub.Export(request)
        except Exception as e:
            logger.error("Error forwarding logs to controller: %s", e, exc_info=True)
            raise

    async def export_traces(self, request):
        """
        Forward traces to the controller.

        Args:
            request: ExportTraceServiceRequest from OpenTelemetry

        Returns:
            ExportTraceServiceResponse from the controller
        """
        try:
            await self._ensure_connected()
            return await self._traces_stub.Export(request)
        except Exception as e:
            logger.error("Error forwarding traces to controller: %s", e, exc_info=True)
            raise

    async def close(self):
        """Close the gRPC channel."""
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._metrics_stub = None
            self._logs_stub = None
            self._traces_stub = None

