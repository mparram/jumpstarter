BUF_IMAGE=docker.io/bufbuild/buf:latest
BUF=podman run --volume "$(shell pwd):/workspace" --workdir /workspace docker.io/bufbuild/buf:latest

all: lint

lint:
	$(BUF) lint

update-otel-protos:
	$(BUF) dep update

protobuf-gen: update-otel-protos
	@echo "Note: protobuf generation happens in controller/ and python/ directories"
	@echo "This target updates OpenTelemetry proto dependencies"

.PHONY: lint update-otel-protos protobuf-gen
