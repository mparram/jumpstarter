"""
HTTP endpoint to expose metrics in Prometheus format.
"""

import logging
from typing import Optional

import aiohttp
from aiohttp import web

from jumpstarter.driver import Driver
from jumpstarter.observability.metrics.collector import MetricsCollector
from jumpstarter.observability.types import ObservabilityConfigV1Alpha1

logger = logging.getLogger(__name__)


class MetricsEndpoint:
    """HTTP endpoint to expose metrics in Prometheus format."""

    def __init__(
        self,
        config: ObservabilityConfigV1Alpha1,
        root_device: Driver,
        exporter_uuid: str,
        exporter_labels: dict[str, str],
    ):
        """
        Initialize the metrics endpoint.

        Args:
            config: Observability configuration (metrics settings)
            root_device: The root driver of the exporter
            exporter_uuid: UUID of the exporter
            exporter_labels: Labels of the exporter
        """
        self.config = config
        self.collector = MetricsCollector(root_device, exporter_uuid, exporter_labels)
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._registered = False
        self._lease_active = False

    def update_status(self, registered: bool, lease_active: bool):
        """
        Update exporter status for metrics.

        Args:
            registered: Whether the exporter is registered
            lease_active: Whether there is an active lease
        """
        self._registered = registered
        self._lease_active = lease_active

    async def _metrics_handler(self, request: web.Request) -> web.Response:
        """
        Handler for the /metrics endpoint.

        Args:
            request: HTTP request

        Returns:
            Response with metrics in Prometheus format
        """
        try:
            metrics_text = self.collector.collect_all_metrics(self._registered, self._lease_active)
            return web.Response(text=metrics_text, content_type="text/plain; version=0.0.4")
        except Exception as e:
            logger.error("Error collecting metrics: %s", e, exc_info=True)
            return web.Response(text=f"# Error collecting metrics: {e}\n", status=500)

    async def start(self):
        """Start the HTTP metrics endpoint."""
        if not self.config.metrics_enabled:
            logger.debug("Metrics endpoint is disabled, not starting")
            return

        self.app = web.Application()
        self.app.router.add_get("/metrics", self._metrics_handler)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(self.runner, self.config.metrics_host, self.config.metrics_port)
        await self.site.start()

        logger.info(
            "Metrics endpoint started on http://%s:%d/metrics",
            self.config.metrics_host,
            self.config.metrics_port,
        )

    async def stop(self):
        """Stop the HTTP metrics endpoint."""
        if not self.config.metrics_enabled or self.runner is None:
            return

        try:
            if self.site is not None:
                await self.site.stop()
            if self.runner is not None:
                await self.runner.cleanup()
            logger.info("Metrics endpoint stopped")
        except Exception as e:
            logger.warning("Error stopping metrics endpoint: %s", e, exc_info=True)
        finally:
            self.site = None
            self.runner = None
            self.app = None

