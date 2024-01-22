import httpx
import pytest
from httpx import Request
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

import logfire
from logfire.testing import TestExporter


@pytest.fixture(autouse=True)  # only applies within this module
def instrument_httpx():
    instrumenter = HTTPXClientInstrumentor()
    instrumenter.instrument()
    yield
    instrumenter.uninstrument()


@pytest.mark.anyio
async def test_httpx_instrumentation(exporter: TestExporter):
    # The purpose of this mock transport is to ensure that the traceparent header is provided
    # without needing to actually make a network request
    def handler(request: Request):
        return httpx.Response(200, headers=request.headers)

    transport = httpx.MockTransport(handler)

    with logfire.span('test span') as span:
        trace_id = span.context.trace_id
        with httpx.Client(transport=transport) as client:
            response = client.get('https://example.org/')
            # Validation of context propagation: ensure that the traceparent header contains the trace ID
            traceparent_header = response.headers['traceparent']
            assert f'{trace_id:032x}' == traceparent_header.split('-')[1]

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'GET',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 3000000000,
            'attributes': {
                'http.method': 'GET',
                'http.url': 'https://example.org/',
                'logfire.span_type': 'span',
                'logfire.msg': 'GET',
                'http.status_code': 200,
            },
        },
        {
            'name': 'test span',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 4000000000,
            'attributes': {
                'code.filepath': 'test_httpx.py',
                'code.lineno': 123,
                'code.function': 'test_httpx_instrumentation',
                'logfire.msg_template': 'test span',
                'logfire.span_type': 'span',
                'logfire.msg': 'test span',
            },
        },
    ]
