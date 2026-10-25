"""Exercise the installed OpenAI SDK over an offline HTTP transport."""

import json

import httpx
import openai
import pytest
import pytest_asyncio

from services.llm.providers.openai_client import OpenAIClient


@pytest_asyncio.fixture
async def sdk_client(monkeypatch):
    responses = []
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return responses.pop(0)

    real_client = openai.AsyncOpenAI
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        monkeypatch.setattr(
            openai,
            "AsyncOpenAI",
            lambda **kwargs: real_client(http_client=http, **kwargs),
        )
        client = OpenAIClient("test-key", "test-model", base_url="https://llm.test/v1")
        yield client, responses, requests
        await client.client.close()


def completion(message):
    return {
        "id": "chat-test",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    }


@pytest.mark.asyncio
async def test_chat_preserves_response_and_usage(sdk_client):
    client, responses, requests = sdk_client
    responses.append(
        httpx.Response(200, json=completion({"role": "assistant", "content": "Answer"}))
    )

    text, usage = await client.chat("Tutor", "Question")

    assert text == "Answer"
    assert usage == {"input_tokens": 7, "output_tokens": 3}
    assert requests[0]["messages"][1] == {"role": "user", "content": "Question"}


@pytest.mark.asyncio
async def test_function_call_arguments_are_decoded(sdk_client):
    client, responses, _ = sdk_client
    responses.append(
        httpx.Response(
            200,
            json=completion(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "search_notes",
                                "arguments": '{"query":"calculus"}',
                            },
                        }
                    ],
                }
            ),
        )
    )

    _, calls, usage = await client.chat_with_tools(
        [{"role": "user", "content": "Find calculus"}],
        [
            {
                "type": "function",
                "function": {"name": "search_notes", "parameters": {"type": "object"}},
            }
        ],
    )

    assert calls == [
        {"id": "call-1", "name": "search_notes", "arguments": {"query": "calculus"}}
    ]
    assert usage["output_tokens"] == 3


@pytest.mark.asyncio
async def test_streaming_preserves_text_and_final_usage(sdk_client):
    client, responses, requests = sdk_client
    base = {
        "id": "chat-test",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test-model",
    }
    chunks = [
        {
            **base,
            "choices": [
                {"index": 0, "delta": {"content": "Answer"}, "finish_reason": None}
            ],
        },
        {
            **base,
            "choices": [],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        },
    ]
    body = (
        "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
        + "data: [DONE]\n\n"
    )
    responses.append(
        httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
    )

    assert [text async for text in client.stream_chat("Tutor", "Question")] == [
        "Answer"
    ]
    assert client.get_last_usage() == {"input_tokens": 7, "output_tokens": 3}
    assert requests[0]["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_authentication_errors_still_reach_the_circuit_breaker(sdk_client):
    client, responses, _ = sdk_client
    responses.append(
        httpx.Response(
            401,
            json={"error": {"message": "Invalid key", "type": "authentication_error"}},
        )
    )

    with pytest.raises(openai.AuthenticationError):
        await client.chat("Tutor", "Question")
    assert not client.is_healthy
