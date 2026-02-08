# Observability

Jumpstarter exporters support comprehensive observability through OpenTelemetry (OTLP), allowing you to collect metrics, logs, and traces from your hardware infrastructure.

## Architecture Overview

The observability architecture in Jumpstarter follows a multi-stage pipeline:

```
┌─────────────────┐
│   Exporter      │
│                 │
│  ┌───────────┐  │
│  │ /metrics  │  │  ← Prometheus format endpoint
│  │ :9090     │  │
│  └─────┬─────┘  │
│        │        │
│        ▼        │
│  ┌───────────┐  │
│  │otel-      │  │  ← External otel-collector on host
│  │collector  │  │     (scrapes /metrics, also can collect logs/traces)
│  └─────┬─────┘  │
│        │        │
│        ▼        │
│  ┌───────────┐  │
│  │OTLP gRPC  │  │  ← OTLP endpoint in exporter
│  │:4317      │  │     (receives from otel-collector)
│  └─────┬─────┘  │
└────────┼────────┘
         │
         │ jumpstarter gRPC
         │
         ▼
┌─────────────────┐
│   Controller    │
│                 │
│  ┌───────────┐  │
│  │OTLP       │  │  ← Receives OTLP signals
│  │Service    │  │
│  └─────┬─────┘  │
│        │        │
│        │        │
│        ▼        │
│  ┌───────────┐  │
│  │OTLP       │  │  ← Re-forwards to platform otel-collector
│  │Exporter   │  │
│  └─────┬─────┘  │
└────────┼────────┘
         │
         │ gRPC (OTLP)
         │
         ▼
┌─────────────────┐
│ Obs. Platform   │
│ otel-collector  │  ← Final destination (otel-collector, Prometheus, Loki, Tempo, Grafana, etc.)
└─────────────────┘
```

### Flow Description

1. **Metrics Endpoint**: The exporter exposes a Prometheus-compatible `/metrics` endpoint on port 9090 (configurable).

2. **External otel-collector**: An OpenTelemetry collector running on the same host as the exporter:
   - Scrapes the `/metrics` endpoint
   - Can collect logs and traces from the exporter / host system
   - Sends all telemetry signals via OTLP-gRPC to the exporter's OTLP endpoint

3. **Exporter OTLP Server**: The exporter receives OTLP signals on port 4317 (configurable) and forwards them to the controller via gRPC.

4. **Controller OTLP Service**: The controller receives OTLP signals from exporters and can optionally re-forward them to a platform-level otel-collector.

5. **Platform otel-collector**: The final destination where all telemetry is aggregated for storage and visualization.

## Building from Source

If you're building Jumpstarter from source or developing the observability features, you **must** generate the OpenTelemetry protobuf definitions before building the project.

### Generating Protobuf Definitions

The observability module uses OpenTelemetry protobuf definitions that need to be generated before the code can be built. Run the following command from the repository root:

```bash
make protobuf-gen
```

This command will:
1. Update OpenTelemetry proto dependencies in `protocol/`
2. Generate Go protobuf code in `controller/`
3. Generate Python protobuf code in `python/` (including OpenTelemetry protos)

## Exporter Configuration

Observability is configured in the exporter configuration file (typically `/etc/jumpstarter/exporters/<name>.yaml`):

```yaml
apiVersion: jumpstarter.dev/v1alpha1
kind: ExporterConfig
metadata:
  namespace: jumpstarter-lab
  name: local
endpoint: grpc.jumpstarter.example.com:8082
tls:
  ca: ''
  insecure: true
token: <your-token>
grpcOptions: {}
description: null
export: {}
observability:
  # Metrics endpoint configuration
  metrics_enabled: true
  metrics_port: 9090
  metrics_host: "0.0.0.0"
  
  # OTLP server configuration
  otlp_enabled: true
  otlp_port: 4317
  otlp_host: "0.0.0.0"
```

### Configuration Options

#### Metrics Endpoint

- **`metrics_enabled`** (default: `false`): Enable or disable the Prometheus metrics endpoint
- **`metrics_port`** (default: `9090`): Port where the `/metrics` endpoint will be exposed
- **`metrics_host`** (default: `"0.0.0.0"`): Host address where the metrics endpoint will bind

#### OTLP Server

- **`otlp_enabled`** (default: `false`): Enable or disable the OTLP gRPC server
- **`otlp_port`** (default: `4317`): Port where the OTLP gRPC server will listen
- **`otlp_host`** (default: `"0.0.0.0"`): Host address where the OTLP server will bind

## External otel-collector Configuration

You need to deploy an OpenTelemetry collector on the same host as the exporter. Here's an example configuration:

```yaml
receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: 'jumpstarter-exporter'
          scrape_interval: 15s
          static_configs:
            - targets: ['localhost:9090']

processors:
  batch:
    timeout: 10s
    send_batch_size: 1024

exporters:
  otlp/exporters:
    endpoint: localhost:4317  # Exporter's OTLP endpoint
    tls:
      insecure: true

service:
  pipelines:
    metrics:
      receivers: [prometheus]
      processors: [batch]
      exporters: [otlp/exporters]
```

### Key Points

- The otel-collector **scrapes** the exporter's `/metrics` endpoint (Prometheus format)
- The otel-collector **sends** all telemetry to the exporter's OTLP endpoint (localhost:4317)

## Controller Configuration

The controller can be configured to re-forward OTLP signals to a platform-level otel-collector using environment variables:

```bash
# Required: OTLP endpoint of the platform collector
OTLP_EXPORTER_ENDPOINT=otel-collector.platform.svc.cluster.local:4317

# Optional: TLS configuration
OTLP_EXPORTER_INSECURE=true  # Set to "true" to disable TLS verification
OTLP_EXPORTER_TLS_CA=/path/to/ca.crt
OTLP_EXPORTER_TLS_CERT=/path/to/client.crt
OTLP_EXPORTER_TLS_KEY=/path/to/client.key
```

### Environment Variables

- **`OTLP_EXPORTER_ENDPOINT`**: The OTLP gRPC endpoint of the platform otel-collector (required to enable forwarding)
- **`OTLP_EXPORTER_INSECURE`**: Set to `"true"` to disable TLS verification (default: false)
- **`OTLP_EXPORTER_TLS_CA`**: Path to CA certificate file for verifying the server
- **`OTLP_EXPORTER_TLS_CERT`**: Path to client certificate file (mutual TLS)
- **`OTLP_EXPORTER_TLS_KEY`**: Path to client private key file (mutual TLS)

If `OTLP_EXPORTER_ENDPOINT` is not set, the controller will receive OTLP signals but won't forward them to an external collector.

## Metrics Exposed

The exporter exposes the following metrics in Prometheus format:

### General Exporter Metrics

- **`jumpstarter_exporter_info`**: Exporter information (labels: `uuid`, `name`, `namespace`)
- **`jumpstarter_drivers_total`**: Total number of drivers in the exporter
- **`jumpstarter_exporter_uptime_seconds`**: Exporter uptime in seconds
- **`jumpstarter_exporter_registered`**: Whether the exporter is registered with the controller (1 = registered, 0 = not registered)
- **`jumpstarter_exporter_lease_active`**: Whether there is an active lease (1 = active, 0 = inactive)

### Driver Metrics

Drivers can expose custom metrics by implementing a `get_metrics()` method that returns a dictionary of metric names and values. These metrics are automatically collected and exposed with the prefix `jumpstarter_driver_` and include driver labels:

- **`driver_uuid`**: UUID of the driver instance
- **`driver_name`**: Class name of the driver
- **`driver_instance`**: Instance name of the driver (or "root" for the root driver)

## Example: Complete Setup

### 1. Configure the Exporter

```yaml
# /etc/jumpstarter/exporters/local.yaml
apiVersion: jumpstarter.dev/v1alpha1
kind: ExporterConfig
metadata:
  namespace: jumpstarter-lab
  name: local
endpoint: grpc.jumpstarter.example.com:8082
tls:
  insecure: true
token: <your-token>
observability:
  metrics_enabled: true
  metrics_port: 9090
  otlp_enabled: true
  otlp_port: 4317
```

### 2. Deploy otel-collector on Host

```yaml
# otel-collector-config.yaml
receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: 'jumpstarter'
          static_configs:
            - targets: ['localhost:9090']

exporters:
  otlp/exporter:
    endpoint: localhost:4317
    tls:
      insecure: true

service:
  pipelines:
    metrics:
      receivers: [prometheus]
      exporters: [otlp/exporter]
```

### 3. Configure Controller

Set environment variables in the controller deployment:

```yaml
# In your controller Deployment or StatefulSet
env:
  - name: OTLP_EXPORTER_ENDPOINT
    value: "otel-collector.platform.svc.cluster.local:4317"
  - name: OTLP_EXPORTER_INSECURE
    value: "true"
```

### 4. Verify

1. Check exporter metrics: `curl http://localhost:9090/metrics`
2. Check otel-collector logs to verify it's scraping and forwarding
3. Check controller logs for OTLP forwarding status
4. Verify telemetry appears in your platform monitoring system

## Troubleshooting

### Metrics Endpoint Not Accessible

- Verify `metrics_enabled: true` in exporter config
- Check that the port is not already in use
- Ensure firewall rules allow access to the metrics port

### OTLP Signals Not Reaching Controller

- Verify `otlp_enabled: true` in exporter config
- Check exporter logs for OTLP server startup messages
- Verify the external otel-collector is configured to send to `localhost:4317`
- Check network connectivity between exporter and controller
- **If building from source**: Ensure you've run `make protobuf-gen` to generate OpenTelemetry protobuf definitions. Missing protos will cause import errors like `ModuleNotFoundError: No module named 'jumpstarter_protocol.opentelemetry'`

### Controller Not Forwarding to Platform Collector

- Verify `OTLP_EXPORTER_ENDPOINT` environment variable is set
- Check controller logs for OTLP exporter client initialization
- Verify TLS configuration if using secure connections
- Test connectivity from controller to platform otel-collector

## Security Considerations

- The metrics endpoint is exposed on `0.0.0.0` by default. Consider restricting access using firewall rules.
- The OTLP server uses insecure connections by default. For production, consider implementing TLS.
- Controller-to-platform collector communication can be secured using TLS certificates via environment variables.

