# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
FROM golang:1.25-alpine@sha256:3eb6c2b3db8d55e38537302edb510b4417f8a115efbd5906d131ceba9468e29a AS backend-build
WORKDIR /src
COPY backend/go.mod backend/go.sum ./
RUN go mod download
COPY backend/ ./
ARG VERSION=railway-demo
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o /out/opennv-validation ./cmd/server

FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32 AS web-build
WORKDIR /src
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG VITE_API_URL=/v1
ARG VITE_DEMO_FALLBACK=false
ENV VITE_API_URL=${VITE_API_URL} VITE_DEMO_FALLBACK=${VITE_DEMO_FALLBACK}
RUN npm run build

FROM gcr.io/distroless/static-debian12:nonroot@sha256:1b7b9f0f0e0a1d2155f531db587cc48ec26aaf97ab64364225f5bf18a054e66a
LABEL org.opencontainers.image.title="OpenNV public emulation demo" \
      org.opencontainers.image.source="https://github.com/open-nv/opennv-deploy" \
      org.opencontainers.image.licenses="Apache-2.0"
WORKDIR /app
COPY --from=backend-build /out/opennv-validation /app/opennv-validation
COPY --from=web-build /src/dist /app/web
COPY validation-packs /app/validation-packs
COPY outputfsm-packs /app/outputfsm-packs
COPY BUILD-MANIFEST.json /app/BUILD-MANIFEST.json
COPY licenses /licenses
ENV PORT=8080
ENV OPENNV_DEMO_MODE=true
ENV WEB_DIR=/app/web
ENV VALIDATION_PACK_ROOT=/app/validation-packs
ENV OUTPUTFSM_PACK_ROOT=/app/outputfsm-packs
EXPOSE 8080
USER nonroot:nonroot
ENTRYPOINT ["/app/opennv-validation"]
