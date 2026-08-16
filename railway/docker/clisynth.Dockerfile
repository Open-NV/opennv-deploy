# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
FROM golang:1.25-alpine@sha256:3eb6c2b3db8d55e38537302edb510b4417f8a115efbd5906d131ceba9468e29a AS build
WORKDIR /src
COPY clisynth/go.mod clisynth/go.sum ./
RUN go mod download
COPY clisynth/ ./
ARG VERSION=railway-demo
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o /out/clisynth ./cmd/clisynth

FROM gcr.io/distroless/static-debian12:nonroot@sha256:1b7b9f0f0e0a1d2155f531db587cc48ec26aaf97ab64364225f5bf18a054e66a
LABEL org.opencontainers.image.title="CliSynth for OpenNV demo" \
      org.opencontainers.image.source="https://github.com/open-nv/opennv-deploy" \
      org.opencontainers.image.licenses="Apache-2.0"
WORKDIR /app
COPY --from=build /out/clisynth /app/clisynth
COPY outputfsm-packs /app/outputfsm-packs
COPY BUILD-MANIFEST.json /app/BUILD-MANIFEST.json
COPY licenses /licenses
ENV PORT=8080
ENV OUTPUTFSM_ROOT=/app/outputfsm-packs
EXPOSE 8080
USER nonroot:nonroot
ENTRYPOINT ["/app/clisynth", "serve"]
