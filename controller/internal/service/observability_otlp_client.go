/*
Copyright 2024.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package service

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"os"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/keepalive"
	metricsv1 "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	logsv1 "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	tracesv1 "go.opentelemetry.io/proto/otlp/collector/trace/v1"
)

// OTLPExporterConfig holds configuration for exporting to an external otel-collector.
type OTLPExporterConfig struct {
	// Endpoint is the OTLP gRPC endpoint (e.g., "otel-collector:4317")
	Endpoint string
	// Insecure disables TLS verification (similar to otel-collector's tls.insecure)
	Insecure bool
	// TLSCertPath is the path to the TLS certificate file (client certificate)
	TLSCertPath string
	// TLSKeyPath is the path to the TLS private key file
	TLSKeyPath string
	// TLSCAPath is the path to the CA certificate file for verifying the server
	TLSCAPath string
	// Timeout is the timeout for gRPC calls
	Timeout time.Duration
}

// OTLPExporterClient is a client for exporting telemetry signals to an external otel-collector.
type OTLPExporterClient struct {
	config       OTLPExporterConfig
	metricsClient metricsv1.MetricsServiceClient
	logsClient    logsv1.LogsServiceClient
	tracesClient  tracesv1.TraceServiceClient
	conn          *grpc.ClientConn
}

// NewOTLPExporterClient creates a new OTLP exporter client.
func NewOTLPExporterClient(config OTLPExporterConfig) (*OTLPExporterClient, error) {
	client := &OTLPExporterClient{
		config: config,
	}

	if err := client.connect(); err != nil {
		return nil, fmt.Errorf("failed to connect to OTLP endpoint: %w", err)
	}

	return client, nil
}

func (c *OTLPExporterClient) connect() error {
	var opts []grpc.DialOption

	// Configure TLS
	if c.config.Insecure {
		opts = append(opts, grpc.WithTransportCredentials(insecure.NewCredentials()))
	} else {
		tlsConfig, err := c.loadTLSConfig()
		if err != nil {
			return fmt.Errorf("failed to load TLS config: %w", err)
		}
		opts = append(opts, grpc.WithTransportCredentials(credentials.NewTLS(tlsConfig)))
	}

	// Configure keepalive
	opts = append(opts, grpc.WithKeepaliveParams(keepalive.ClientParameters{
		Time:                10 * time.Second,
		Timeout:             3 * time.Second,
		PermitWithoutStream: true,
	}))

	// Set default timeout if not specified
	timeout := c.config.Timeout
	if timeout == 0 {
		timeout = 10 * time.Second
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	conn, err := grpc.DialContext(ctx, c.config.Endpoint, opts...)
	if err != nil {
		return fmt.Errorf("failed to dial OTLP endpoint: %w", err)
	}

	c.conn = conn
	c.metricsClient = metricsv1.NewMetricsServiceClient(conn)
	c.logsClient = logsv1.NewLogsServiceClient(conn)
	c.tracesClient = tracesv1.NewTraceServiceClient(conn)

	return nil
}

// loadTLSConfig loads TLS configuration from files (similar to otel-collector).
func (c *OTLPExporterClient) loadTLSConfig() (*tls.Config, error) {
	tlsConfig := &tls.Config{}

	// Load CA certificate if provided
	if c.config.TLSCAPath != "" {
		caCert, err := os.ReadFile(c.config.TLSCAPath)
		if err != nil {
			return nil, fmt.Errorf("failed to read CA certificate: %w", err)
		}
		caCertPool := x509.NewCertPool()
		if !caCertPool.AppendCertsFromPEM(caCert) {
			return nil, fmt.Errorf("failed to parse CA certificate")
		}
		tlsConfig.RootCAs = caCertPool
	}

	// Load client certificate and key if provided
	if c.config.TLSCertPath != "" && c.config.TLSKeyPath != "" {
		cert, err := tls.LoadX509KeyPair(c.config.TLSCertPath, c.config.TLSKeyPath)
		if err != nil {
			return nil, fmt.Errorf("failed to load client certificate: %w", err)
		}
		tlsConfig.Certificates = []tls.Certificate{cert}
	}

	return tlsConfig, nil
}

// ExportMetrics exports metrics to the otel-collector.
func (c *OTLPExporterClient) ExportMetrics(ctx context.Context, req *metricsv1.ExportMetricsServiceRequest) (*metricsv1.ExportMetricsServiceResponse, error) {
	if c.metricsClient == nil {
		return nil, fmt.Errorf("metrics client not initialized")
	}
	return c.metricsClient.Export(ctx, req)
}

// ExportLogs exports logs to the otel-collector.
func (c *OTLPExporterClient) ExportLogs(ctx context.Context, req *logsv1.ExportLogsServiceRequest) (*logsv1.ExportLogsServiceResponse, error) {
	if c.logsClient == nil {
		return nil, fmt.Errorf("logs client not initialized")
	}
	return c.logsClient.Export(ctx, req)
}

// ExportTraces exports traces to the otel-collector.
func (c *OTLPExporterClient) ExportTraces(ctx context.Context, req *tracesv1.ExportTraceServiceRequest) (*tracesv1.ExportTraceServiceResponse, error) {
	if c.tracesClient == nil {
		return nil, fmt.Errorf("traces client not initialized")
	}
	return c.tracesClient.Export(ctx, req)
}

// Close closes the gRPC connection.
func (c *OTLPExporterClient) Close() error {
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}

