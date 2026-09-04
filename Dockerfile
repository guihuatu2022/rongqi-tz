FROM golang:1.22-alpine AS build
WORKDIR /app
COPY go.mod main.go ./
COPY web ./web
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o probe main.go

FROM alpine:3.20
RUN adduser -D -H -u 10001 probeuser
COPY --from=build /app/probe /probe
USER probeuser
EXPOSE 8080
ENV PORT=8080
ENTRYPOINT ["/probe"]
