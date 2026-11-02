ARG GO_VERSION_TAG=1.26-alpine

# build
FROM golang:${GO_VERSION_TAG} AS builder

WORKDIR /build

COPY go.mod go.sum *.go ./
RUN go mod tidy \
    && go mod download \
    && go build -o /extproc .

RUN go install github.com/grpc-ecosystem/grpc-health-probe@v0.4.39

FROM golang:${GO_VERSION_TAG}

COPY --from=builder /extproc /extproc
COPY --from=builder /go/bin/grpc-health-probe /grpc-health-probe

EXPOSE 50051
EXPOSE 9090

ENTRYPOINT [ "/extproc" ]
