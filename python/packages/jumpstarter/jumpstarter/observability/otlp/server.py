"""
OTLP gRPC server for receiving telemetry signals from otel-collector.

This server implements the OpenTelemetry collector services (MetricsService,
LogsService, TracesService) and forwards the signals to the controller.
"""

import logging
from typing import Callable, Optional

import grpc

from jumpstarter.observability.otlp.controller_client import ObservabilityControllerClient
from jumpstarter.observability.types import ObservabilityConfigV1Alpha1

# These imports will be available after protobuf generation
# For now, we'll use try/except to handle missing imports gracefully
try:
    from jumpstarter_protocol.opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2, metrics_service_pb2_grpc
    from jumpstarter_protocol.opentelemetry.proto.collector.logs.v1 import logs_service_pb2, logs_service_pb2_grpc
    from jumpstarter_protocol.opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc
    OTLP_AVAILABLE = True
except ImportError:
    OTLP_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(
        "OpenTelemetry protos not available. OTLP server will not function. "
        "Run 'make protobuf-gen' to generate protos."
    )

logger = logging.getLogger(__name__)


class OTLPServer:
    """OTLP gRPC server that receives telemetry signals and forwards them to the controller."""

    def __init__(
        self,
        config: ObservabilityConfigV1Alpha1,
        channel_factory: Callable[[], grpc.aio.Channel],
    ):
        """
        Initialize the OTLP server.

        Args:
            config: Observability configuration (OTLP settings)
            channel_factory: Async callable that returns a gRPC channel to the controller
        """
        if not OTLP_AVAILABLE:
            raise ImportError(
                "OpenTelemetry protos are not available. "
                "Please run 'make protobuf-gen' in the protocol directory to generate them."
            )

        self.config = config
        self.controller_client = ObservabilityControllerClient(channel_factory)
        self.server: Optional[grpc.aio.Server] = None
        self._metrics_servicer: Optional[_MetricsServicer] = None
        self._logs_servicer: Optional[_LogsServicer] = None
        self._traces_servicer: Optional[_TracesServicer] = None

    async def start(self):
        """Start the OTLP gRPC server."""
        if not self.config.otlp_enabled:
            logger.debug("OTLP server is disabled, not starting")
            return

        if not OTLP_AVAILABLE:
            logger.error("Cannot start OTLP server: OpenTelemetry protos not available")
            return

        self.server = grpc.aio.server()

        # Create servicers
        self._metrics_servicer = _MetricsServicer(self.controller_client)
        self._logs_servicer = _LogsServicer(self.controller_client)
        self._traces_servicer = _TracesServicer(self.controller_client)

        # Register services
        metrics_service_pb2_grpc.add_MetricsServiceServicer_to_server(
            self._metrics_servicer, self.server
        )
        logs_service_pb2_grpc.add_LogsServiceServicer_to_server(
            self._logs_servicer, self.server
        )
        trace_service_pb2_grpc.add_TraceServiceServicer_to_server(
            self._traces_servicer, self.server
        )

        # Listen on the configured port
        listen_addr = f"{self.config.otlp_host}:{self.config.otlp_port}"
        self.server.add_insecure_port(listen_addr)
        await self.server.start()

        logger.info("OTLP gRPC server started on %s", listen_addr)

    async def stop(self):
        """Stop the OTLP gRPC server."""
        if not self.config.otlp_enabled or self.server is None:
            return

        try:
            await self.server.stop(grace=5)
            await self.controller_client.close()
            logger.info("OTLP gRPC server stopped")
        except Exception as e:
            logger.warning("Error stopping OTLP server: %s", e, exc_info=True)
        finally:
            self.server = None
            self._metrics_servicer = None
            self._logs_servicer = None
            self._traces_servicer = None


class _MetricsServicer(metrics_service_pb2_grpc.MetricsServiceServicer):
    """Internal servicer for OpenTelemetry MetricsService."""

    def __init__(self, controller_client: ObservabilityControllerClient):
        self.controller_client = controller_client

    async def Export(self, request, context):
        """Handle ExportMetricsServiceRequest."""
        try:
            response = await self.controller_client.export_metrics(request)
            return response
        except Exception as e:
            logger.error("Error handling metrics export: %s", e, exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            # Return empty response on error
            return metrics_service_pb2.ExportMetricsServiceResponse()


class _LogsServicer(logs_service_pb2_grpc.LogsServiceServicer):
    """Internal servicer for OpenTelemetry LogsService."""

    def __init__(self, controller_client: ObservabilityControllerClient):
        self.controller_client = controller_client

    async def Export(self, request, context):
        """Handle ExportLogsServiceRequest."""
        try:
            response = await self.controller_client.export_logs(request)
            return response
        except Exception as e:
            logger.error("Error handling logs export: %s", e, exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            # Return empty response on error
            return logs_service_pb2.ExportLogsServiceResponse()


class _TracesServicer(trace_service_pb2_grpc.TraceServiceServicer):
    """Internal servicer for OpenTelemetry TraceService."""

    def __init__(self, controller_client: ObservabilityControllerClient):
        self.controller_client = controller_client

    async def Export(self, request, context):
        """Handle ExportTraceServiceRequest."""
        try:
            response = await self.controller_client.export_traces(request)
            return response
        except Exception as e:
            logger.error("Error handling traces export: %s", e, exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            # Return empty response on error
            return trace_service_pb2.ExportTraceServiceResponse()

