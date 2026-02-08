"""
Metrics collector for Jumpstarter exporters.

Collects general application metrics and driver metrics.
"""

import logging
import time

from jumpstarter.driver import Driver

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Centralized metrics collector."""

    def __init__(self, root_device: Driver, exporter_uuid: str, exporter_labels: dict[str, str]):
        """
        Initialize the metrics collector.

        Args:
            root_device: The root driver of the exporter
            exporter_uuid: UUID of the exporter
            exporter_labels: Labels of the exporter (name, namespace, etc.)
        """
        self.root_device = root_device
        self.exporter_uuid = exporter_uuid
        self.exporter_labels = exporter_labels
        self._start_time = time.time()

    def collect_general_metrics(self, registered: bool, lease_active: bool) -> list[tuple[str, float, dict[str, str]]]:
        """
        Collect general exporter metrics.

        Args:
            registered: Whether the exporter is registered with the controller
            lease_active: Whether there is an active lease

        Returns:
            List of tuples (metric_name, value, labels) for Prometheus format
        """
        metrics = []

        # Exporter information
        labels = {
            "uuid": self.exporter_uuid,
            "name": self.exporter_labels.get("jumpstarter.dev/name", "unknown"),
            "namespace": self.exporter_labels.get("jumpstarter.dev/namespace", "unknown"),
        }
        metrics.append(("jumpstarter_exporter_info", 1.0, labels))

        # Total number of drivers
        driver_count = len(list(self.root_device.enumerate()))
        metrics.append(("jumpstarter_drivers_total", float(driver_count), {}))

        # Uptime
        uptime = time.time() - self._start_time
        metrics.append(("jumpstarter_exporter_uptime_seconds", uptime, {}))

        # Registration status
        metrics.append(("jumpstarter_exporter_registered", 1.0 if registered else 0.0, {}))

        # Lease status
        metrics.append(("jumpstarter_exporter_lease_active", 1.0 if lease_active else 0.0, {}))

        return metrics

    def collect_driver_metrics(self) -> list[tuple[str, float, dict[str, str]]]:
        """
        Collect metrics from all drivers.

        Returns:
            List of tuples (metric_name, value, labels) for Prometheus format
        """
        metrics = []

        for uuid, parent, name, driver in self.root_device.enumerate():
            try:
                # Try to get metrics from driver if it implements get_metrics()
                if hasattr(driver, "get_metrics"):
                    driver_metrics = driver.get_metrics()
                    if driver_metrics and isinstance(driver_metrics, dict):
                        # Add driver labels to each metric
                        driver_name = driver.__class__.__name__
                        driver_labels = {
                            "driver_uuid": str(uuid),
                            "driver_name": driver_name,
                            "driver_instance": name or "root",
                        }

                        for metric_name, metric_value in driver_metrics.items():
                            # Ensure metric name has the correct prefix
                            if not metric_name.startswith("jumpstarter_"):
                                metric_name = f"jumpstarter_driver_{metric_name}"

                            # Normalize metric name for Prometheus (only letters, numbers and underscores)
                            metric_name = metric_name.replace("-", "_").replace(".", "_")

                            # Convert value to float if necessary
                            try:
                                float_value = float(metric_value)
                                metrics.append((metric_name, float_value, driver_labels))
                            except (ValueError, TypeError):
                                logger.warning(
                                    "Driver %s returned invalid metric value for %s: %s",
                                    driver_name,
                                    metric_name,
                                    metric_value,
                                )
            except Exception as e:
                logger.warning("Error collecting metrics from driver %s: %s", driver.__class__.__name__, e, exc_info=True)

        return metrics

    def collect_all_metrics(self, registered: bool, lease_active: bool) -> str:
        """
        Collect all metrics and format them in Prometheus format.

        Args:
            registered: Whether the exporter is registered with the controller
            lease_active: Whether there is an active lease

        Returns:
            String with metrics in Prometheus format
        """
        all_metrics = []
        all_metrics.extend(self.collect_general_metrics(registered, lease_active))
        all_metrics.extend(self.collect_driver_metrics())

        # Format in Prometheus format
        lines = []
        for metric_name, metric_value, labels in sorted(all_metrics):
            if labels:
                # Format labels: label1="value1",label2="value2"
                labels_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
                lines.append(f"{metric_name}{{{labels_str}}} {metric_value}")
            else:
                lines.append(f"{metric_name} {metric_value}")

        return "\n".join(lines) + "\n"

