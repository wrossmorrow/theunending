package main

import (
	"log"
	"strings"

	ep "github.com/wrossmorrow/envoy-extproc-sdk-go"
)

const unauthnResponse = "{\"error\": \"Unauthorized\"}"
const unauthzResponse = "{\"error\": \"Forbidden\"}"

type authRequestProcessor struct {
	opts   *ep.ProcessingOptions
	tokens map[string][]string
}

func (s *authRequestProcessor) GetName() string {
	return "theunending-admin-auth"
}

func (s *authRequestProcessor) GetOptions() *ep.ProcessingOptions {
	return s.opts
}

func (s *authRequestProcessor) ProcessRequestHeaders(ctx *ep.RequestContext, headers ep.AllHeaders) error {
	auth, ok := headers.Get("authorization")
	if !ok {
		return ctx.CancelRequest(401, nil, unauthnResponse)
	}
	if len(auth) == 0 {
		return ctx.CancelRequest(401, nil, unauthnResponse)
	}
	if !strings.HasPrefix(auth, "Bearer ") {
		return ctx.CancelRequest(401, nil, unauthnResponse)
	}

	token := strings.TrimPrefix(auth, "Bearer ")
	paths, ok := s.tokens[token]
	if !ok {
		return ctx.CancelRequest(403, nil, unauthzResponse)
	}

	path := ctx.Path
	log.Printf("Path/Paths allowed: %s, %v\n", path, paths)
	// TODO: look into paths against _this_ path

	return ctx.ContinueRequest()
}

func (s *authRequestProcessor) ProcessRequestBody(ctx *ep.RequestContext, body []byte) error {
	return ctx.ContinueRequest()
}

func (s *authRequestProcessor) ProcessRequestTrailers(ctx *ep.RequestContext, trailers ep.AllHeaders) error {
	return ctx.ContinueRequest()
}

func (s *authRequestProcessor) ProcessResponseHeaders(ctx *ep.RequestContext, headers ep.AllHeaders) error {
	return ctx.ContinueRequest()
}

func (s *authRequestProcessor) ProcessResponseBody(ctx *ep.RequestContext, body []byte) error {
	return ctx.ContinueRequest()
}

func (s *authRequestProcessor) ProcessResponseTrailers(ctx *ep.RequestContext, trailers ep.AllHeaders) error {
	return ctx.ContinueRequest()
}

func (s *authRequestProcessor) ErrorHandler(ctx *ep.RequestContext, phase int, err error) {
	log.Printf("Error in phase %s: %v", ep.RequestPhaseToString(phase), err)
}

func (s *authRequestProcessor) Close(gracePeriodSeconds int32) error {
	log.Printf("Closing")
	return nil
}
