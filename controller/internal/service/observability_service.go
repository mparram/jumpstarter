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
	"fmt"
	"os"
	"time"

	jumpstarterdevv1alpha1 "github.com/jumpstarter-dev/jumpstarter-controller/api/v1alpha1"
	"github.com/jumpstarter-dev/jumpstarter-controller/internal/authentication"
	"github.com/jumpstarter-dev/jumpstarter-controller/internal/authorization"
	"github.com/jumpstarter-dev/jumpstarter-controller/internal/oidc"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apiserver/pkg/authorization/authorizer"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	logsv1 "go.opentelemetry.io/proto/otlp/collector/logs/v1"
	metricsv1 "go.opentelemetry.io/proto/otlp/collector/metrics/v1"
	tracesv1 "go.opentelemetry.io/proto/otlp/collector/trace/v1"
)

// ObservabilityService implements OpenTelemetry's OTLP services for receiving telemetry signals from exporters.
// It implements MetricsServiceServer, LogsServiceServer, and TraceServiceServer.
type ObservabilityService struct {
	metricsv1.UnimplementedMetricsServiceServer
	logsv1.UnimplementedLogsServiceServer
	tracesv1.UnimplementedTraceServiceServer
	Client       client.WithWatch
	Scheme       *runtime.Scheme
	Authn        authentication.ContextAuthenticator
	Authz        authorizer.Authorizer
	Attr         authorization.ContextAttributesGetter
	otlpExporter *OTLPExporterClient
}

// metricsService wraps ObservabilityService to implement MetricsServiceServer
type metricsService struct {
	*ObservabilityService
}

// logsService wraps ObservabilityService to implement LogsServiceServer
type logsService struct {
	*ObservabilityService
}

// tracesService wraps ObservabilityService to implement TraceServiceServer
type tracesService struct {
	*ObservabilityService
}

func (s *ObservabilityService) authenticateExporter(ctx context.Context) (*jumpstarterdevv1alpha1.Exporter, error) {
	return oidc.VerifyExporterObjectToken(
		ctx,
		s.Authn,
		s.Authz,
		s.Attr,
		s.Client,
	)
}

// Export implements MetricsServiceServer.Export
func (s *metricsService) Export(ctx context.Context, req *metricsv1.ExportMetricsServiceRequest) (*metricsv1.ExportMetricsServiceResponse, error) {
	logger := log.FromContext(ctx)

	// Authenticate the exporter
	_, err := s.authenticateExporter(ctx)
	if err != nil {
		logger.Error(err, "Failed to authenticate exporter for metrics export")
		return nil, err
	}

	logger.V(1).Info("Received metrics export request", "resource_metrics_count", len(req.ResourceMetrics))

	// Forward to external otel-collector if configured
	if s.ObservabilityService.otlpExporter != nil {
		if _, err := s.ObservabilityService.otlpExporter.ExportMetrics(ctx, req); err != nil {
			logger.Error(err, "Failed to forward metrics to otel-collector")
			// Don't fail the request if forwarding fails, just log the error
		}
	}

	return &metricsv1.ExportMetricsServiceResponse{}, nil
}

// Export implements LogsServiceServer.Export
func (s *logsService) Export(ctx context.Context, req *logsv1.ExportLogsServiceRequest) (*logsv1.ExportLogsServiceResponse, error) {
	logger := log.FromContext(ctx)

	// Authenticate the exporter
	_, err := s.ObservabilityService.authenticateExporter(ctx)
	if err != nil {
		logger.Error(err, "Failed to authenticate exporter for logs export")
		return nil, err
	}

	logger.V(1).Info("Received logs export request", "resource_logs_count", len(req.ResourceLogs))

	// Forward to external otel-collector if configured
	if s.ObservabilityService.otlpExporter != nil {
		if _, err := s.ObservabilityService.otlpExporter.ExportLogs(ctx, req); err != nil {
			logger.Error(err, "Failed to forward logs to otel-collector")
			// Don't fail the request if forwarding fails, just log the error
		}
	}

	return &logsv1.ExportLogsServiceResponse{}, nil
}

// Export implements TraceServiceServer.Export
func (s *tracesService) Export(ctx context.Context, req *tracesv1.ExportTraceServiceRequest) (*tracesv1.ExportTraceServiceResponse, error) {
	logger := log.FromContext(ctx)

	// Authenticate the exporter
	_, err := s.ObservabilityService.authenticateExporter(ctx)
	if err != nil {
		logger.Error(err, "Failed to authenticate exporter for traces export")
		return nil, err
	}

	logger.V(1).Info("Received traces export request", "resource_spans_count", len(req.ResourceSpans))

	// Forward to external otel-collector if configured
	if s.ObservabilityService.otlpExporter != nil {
		if _, err := s.ObservabilityService.otlpExporter.ExportTraces(ctx, req); err != nil {
			logger.Error(err, "Failed to forward traces to otel-collector")
			// Don't fail the request if forwarding fails, just log the error
		}
	}

	return &tracesv1.ExportTraceServiceResponse{}, nil
}

// Start implements manager.Runnable interface.
// Initializes the OTLP exporter client if configured.
func (s *ObservabilityService) Start(ctx context.Context) error {
	logger := log.FromContext(ctx)

	// Check if OTLP exporter is configured via environment variables
	endpoint := os.Getenv("OTLP_EXPORTER_ENDPOINT")
	if endpoint == "" {
		logger.V(1).Info("OTLP exporter not configured, skipping initialization")
		// Wait for context cancellation
		<-ctx.Done()
		return nil
	}

	config := OTLPExporterConfig{
		Endpoint:    endpoint,
		Insecure:    os.Getenv("OTLP_EXPORTER_INSECURE") == "true",
		TLSCertPath: os.Getenv("OTLP_EXPORTER_TLS_CERT"),
		TLSKeyPath:  os.Getenv("OTLP_EXPORTER_TLS_KEY"),
		TLSCAPath:   os.Getenv("OTLP_EXPORTER_TLS_CA"),
		Timeout:     10 * time.Second,
	}

	client, err := NewOTLPExporterClient(config)
	if err != nil {
		return fmt.Errorf("failed to initialize OTLP exporter client: %w", err)
	}

	s.otlpExporter = client
	logger.Info("OTLP exporter client initialized", "endpoint", endpoint, "insecure", config.Insecure)

	// Wait for context cancellation and close the client
	<-ctx.Done()
	logger.Info("Shutting down OTLP exporter client")
	if err := client.Close(); err != nil {
		logger.Error(err, "Error closing OTLP exporter client")
	}

	return nil
}

// SetupWithManager sets up the controller with the Manager.
func (s *ObservabilityService) SetupWithManager(mgr ctrl.Manager) error {
	return mgr.Add(s)
}
