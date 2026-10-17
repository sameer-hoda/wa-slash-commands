# ── build the Go bridge ─────────────────────────────────────────────
FROM golang:1.26-bookworm AS gobuild
WORKDIR /src/bridge
COPY bridge/go.mod bridge/go.sum ./
RUN go mod download
COPY bridge/ ./
RUN CGO_ENABLED=1 go build -o /out/wa-bridge .

# ── runtime: bridge + python command engine ─────────────────────────
FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=gobuild /out/wa-bridge /app/bridge/wa-bridge

ENV STORE_DIR=/data
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
RUN mkdir -p /data
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=60s CMD python3 -c "import os,urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8081')+'/health',timeout=4).status==200 else 1)"

CMD ["/app/bridge/wa-bridge"]
