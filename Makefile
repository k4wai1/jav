VERSION ?= 0.1.0
LDFLAGS = -s -w -X main.version=$(VERSION)
BIN = dist/jav-linux-amd64

.PHONY: build build-all test vet tools-list-diff clean

build:
	mkdir -p dist
	CGO_ENABLED=0 go build -trimpath -ldflags "$(LDFLAGS)" -o $(BIN) ./cmd/jav

build-all:
	mkdir -p dist
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags "$(LDFLAGS)" -o dist/jav-linux-amd64 ./cmd/jav
	CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -trimpath -ldflags "$(LDFLAGS)" -o dist/jav-linux-arm64 ./cmd/jav
	CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -trimpath -ldflags "$(LDFLAGS)" -o dist/jav-darwin-arm64 ./cmd/jav
	CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "$(LDFLAGS)" -o dist/jav-windows-amd64.exe ./cmd/jav

test:
	go test ./...

vet:
	go vet ./...

# Compara tools/list Go vs Python (nombre + required + tipos). Diff vacío = OK.
# Se corre desde la raíz del repo (el Makefile vive aquí tras la reubicación
# de go-mcp/ → raíz; sin `cd ..`).
tools-list-diff: build
	uv run --project mcp-server --with ./mcp-server python scripts/tools-list-diff.py --bin $(BIN)

clean:
	rm -rf dist
