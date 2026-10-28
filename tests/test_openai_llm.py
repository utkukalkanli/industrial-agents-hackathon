"""agent/openai_llm.py and agent/llm_client.py offline: Anthropic-shaped requests → Responses API and back."""

from types import SimpleNamespace

import anthropic
import httpx2
import openai
import pytest
from anthropic.types.beta import BetaTextBlock, BetaToolUseBlock

from agent import llm_client
from agent.guide import llm_mode, make_client
from agent.llm_cache import decision_key
from agent.openai_llm import (
    OpenAIClient,
    anthropic_error,
    anthropic_message,
    openai_model,
    openai_request,
)
from backend.service_errors import code_of


def usage(input_tokens=120, output_tokens=30, cached=100):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                           input_tokens_details=SimpleNamespace(cached_tokens=cached))


def text_item(text):
    return SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text=text)])


def call_item(call_id, name, arguments):
    return SimpleNamespace(type="function_call", call_id=call_id, name=name, arguments=arguments)


class FakeResponses:
    def __init__(self, outputs):
        self.outputs, self.requests = list(outputs), []

    def create(self, **request):
        self.requests.append(request)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return SimpleNamespace(id="resp_1", output=output, usage=usage(), incomplete_details=None)


def client_with(*outputs):
    fake = SimpleNamespace(responses=FakeResponses(outputs))
    return OpenAIClient(client=fake), fake.responses


def test_claude_models_map_by_family_and_others_pass_through(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert openai_model("claude-opus-5-5") == "gpt-6.1-sol"
    assert openai_model("claude-sonnet-5-5") == "gpt-6.1-terra"
    assert openai_model("claude-haiku-5-5") == "gpt-6-luna"
    assert openai_model("gpt-6-astra") == "gpt-6-astra"
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-astra")
    assert openai_model("claude-opus-5") == "gpt-6-astra"


def test_request_maps_system_history_tools_and_output_config():
    history = [
        {"role": "user", "content": [{"type": "text", "text": "Where is the printer?"},
                                     {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                                  "data": "AAA"}}]},
        {"role": "assistant", "content": [BetaTextBlock(type="text", text="Let me look."),
                                          BetaToolUseBlock(type="tool_use", id="call_1", name="locate",
                                                           input={"query": "printer"})]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": '{"n": 1}'},
                                     {"type": "tool_result", "tool_use_id": "call_2", "is_error": True,
                                      "content": [{"type": "text", "text": "no such room"}]}]},
    ]
    request = openai_request({
        "model": "claude-opus-5-5", "max_tokens": 16000, "messages": history,
        "system": [{"type": "text", "text": "Rules."}, {"type": "text", "text": "Overview.", "cache_control": {}}],
        "tools": [{"name": "locate", "description": "Find.", "input_schema": {"type": "object", "properties": {}}}],
        "tool_choice": {"type": "any"}, "cache_control": {"type": "ephemeral"}, "betas": ["x"], "fallbacks": "default",
        "speed": "fast", "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": {"type": "object"}}},
    })
    assert request["instructions"] == "Rules.\n\nOverview."
    assert request["max_output_tokens"] == 16000 and request["store"] is False
    assert request["reasoning"] == {"effort": "low"}
    assert request["text"]["format"]["type"] == "json_schema" and request["text"]["format"]["strict"] is False
    assert request["tools"] == [{"type": "function", "name": "locate", "description": "Find.",
                                 "parameters": {"type": "object", "properties": {}}, "strict": False}]
    assert request["tool_choice"] == "required"
    assert not {"cache_control", "betas", "fallbacks", "speed", "system", "messages"} & set(request)
    items = request["input"]
    assert items[0] == {"role": "user", "content": [{"type": "input_text", "text": "Where is the printer?"},
                                                    {"type": "input_image", "image_url": "data:image/png;base64,AAA"}]}
    assert items[1] == {"role": "assistant", "content": "Let me look."}
    assert items[2] == {"type": "function_call", "call_id": "call_1", "name": "locate",
                        "arguments": '{"query": "printer"}'}
    assert items[3] == {"type": "function_call_output", "call_id": "call_1", "output": '{"n": 1}'}
    assert items[4] == {"type": "function_call_output", "call_id": "call_2", "output": "Error: no such room"}


def test_tool_result_with_an_image_keeps_both_parts():
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "BBB"}}
    request = openai_request({"model": "m", "messages": [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "c", "content": [{"type": "text", "text": "plan"}, image]}]}]})
    assert request["input"][0]["output"] == [{"type": "input_text", "text": "plan"},
                                             {"type": "input_image", "image_url": "data:image/png;base64,BBB"}]


def test_response_becomes_an_anthropic_message_with_tool_use_and_usage():
    client, fake = client_with([text_item("Checking."), call_item("call_9", "locate", '{"query": "toilet"}')],
                               [text_item("It is on floor 1.")])
    first = client.beta.messages.create(model="claude-opus-5-5", max_tokens=10, messages=[
        {"role": "user", "content": "toilet?"}])
    assert first.stop_reason == "tool_use" and first.model == "claude-opus-5-5"
    assert [block.type for block in first.content] == ["text", "tool_use"]
    assert first.content[1].id == "call_9" and first.content[1].input == {"query": "toilet"}
    assert first.usage.input_tokens == 20 and first.usage.cache_read_input_tokens == 100
    assert fake.requests[0]["model"] == "gpt-6.1-sol"
    second = client.messages.create(model="claude-opus-5-5", max_tokens=10, messages=[
        {"role": "user", "content": "toilet?"}, {"role": "assistant", "content": first.content},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_9", "content": "ok"}]}])
    assert second.stop_reason == "end_turn" and second.content[0].text == "It is on floor 1."
    assert fake.requests[1]["input"][2]["type"] == "function_call"


def status_error(status, message):
    response = httpx2.Response(status, request=httpx2.Request("POST", "https://api.openai.com/v1/responses"))
    return openai.APIStatusError(message, response=response, body=None)


def test_openai_errors_become_the_anthropic_classes_the_backend_handles():
    limited = anthropic_error(status_error(429, "Rate limit reached"))
    assert isinstance(limited, anthropic.RateLimitError) and code_of(limited) == "busy"
    quota = anthropic_error(status_error(429, "You exceeded your current quota, please check your plan and billing"))
    assert code_of(quota) == "credits"
    assert code_of(anthropic_error(status_error(401, "bad key"))) == "auth"
    assert code_of(anthropic_error(status_error(503, "down"))) == "unavailable"
    timeout = anthropic_error(openai.APITimeoutError(request=httpx2.Request("POST", "https://x")))
    assert isinstance(timeout, anthropic.APIConnectionError) and code_of(timeout) == "offline"
    client, _ = client_with(status_error(429, "Rate limit reached"))
    with pytest.raises(anthropic.RateLimitError):
        client.beta.messages.create(model="m", messages=[{"role": "user", "content": "hi"}])


def test_provider_follows_the_variable_then_the_keys(monkeypatch):
    for name in ("LLM_PROVIDER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GUIDE_LLM"):
        monkeypatch.delenv(name, raising=False)
    assert llm_client.provider() == "openai" and llm_mode() == "offline"  # no key: OpenAI, so its cache replays
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert llm_client.provider() == "anthropic"  # only Claude's key: Claude
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert llm_client.provider() == "openai" and llm_mode() == "openai"
    assert isinstance(make_client(), OpenAIClient) and llm_client.live(make_client())
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert llm_mode() == "offline"  # Claude picked but no Anthropic key
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert llm_mode() == "anthropic" and isinstance(make_client(), anthropic.Anthropic)
    monkeypatch.setenv("GUIDE_LLM", "offline")
    assert llm_mode() == "offline" and not llm_client.live(make_client())


def test_service_tier_goes_with_the_big_model_only(monkeypatch):
    for name in ("OPENAI_SERVICE_TIER", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    hi = [{"role": "user", "content": "hi"}]
    assert openai_request({"model": "claude-opus-5-5", "messages": hi})["service_tier"] == "ultrafast"
    assert "service_tier" not in openai_request({"model": "claude-haiku-5-5", "messages": hi})
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.5")  # no ultrafast tier
    assert "service_tier" not in openai_request({"model": "claude-opus-5-5", "messages": hi})
    monkeypatch.setenv("OPENAI_SERVICE_TIER", "priority")
    assert openai_request({"model": "claude-opus-5-5", "messages": hi})["service_tier"] == "priority"


def test_a_tool_call_cut_off_by_the_token_limit_stops_with_max_tokens():
    response = SimpleNamespace(id="resp_2", output=[call_item("call_9", "trace", '{"points": [[0, 0], [1')],
                               usage=usage(), incomplete_details=SimpleNamespace(reason="max_output_tokens"))
    assert anthropic_message(response, "claude-opus-5-5").stop_reason == "max_tokens"


def test_guide_llm_naming_a_provider_wins_over_the_keys(monkeypatch):
    for name in ("LLM_PROVIDER", "GUIDE_LLM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert llm_mode() == "openai"
    monkeypatch.setenv("GUIDE_LLM", "anthropic")
    assert llm_mode() == "anthropic" and isinstance(make_client(), anthropic.Anthropic)
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("GUIDE_LLM", "openai")
    assert llm_mode() == "openai"


def test_key_name_follows_the_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert llm_client.key_name() == "OPENAI_API_KEY"
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert llm_client.key_name() == "ANTHROPIC_API_KEY"


def test_cached_decisions_are_kept_apart_per_provider(monkeypatch):
    building = SimpleNamespace(data={"spaces": []})
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    claude = decision_key("parser", "3", building, "Where is room 1?")
    assert claude.count("/") == 3  # Claude's keys keep the committed format, so its cached decisions still replay
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert decision_key("parser", "3", building, "Where is room 1?") != claude


def test_the_builder_uses_the_provider_guide_llm_names(monkeypatch):
    from agent.builder import make_builder_client

    for name in ("LLM_PROVIDER", "GUIDE_LLM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert isinstance(make_builder_client(), OpenAIClient)
    monkeypatch.setenv("GUIDE_LLM", "anthropic")
    assert isinstance(make_builder_client(), anthropic.Anthropic)


def test_kept_content_drops_tool_calls_of_a_cut_off_reply():
    from agent.offline_llm import message, text_block, tool_use

    whole = message(text_block("Let me look."), tool_use("locate", {"query": "x"}))
    assert llm_client.kept_content(whole) == list(whole.content)
    cut = message(text_block("Let me look."), tool_use("locate", {"query": "x"}), stop_reason="max_tokens")
    assert [block.type for block in llm_client.kept_content(cut)] == ["text"]
    only_call = message(tool_use("locate", {"query": "x"}), stop_reason="max_tokens")
    placeholder = llm_client.kept_content(only_call)
    assert [(block.type, block.text) for block in placeholder] == [("text", "(cut off by the token limit)")]


def test_without_an_openai_key_the_client_builds_and_requests_fail_as_auth(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = OpenAIClient()
    with pytest.raises(anthropic.AuthenticationError) as raised:
        client.beta.messages.create(model="claude-opus-5-5", max_tokens=10,
                                    messages=[{"role": "user", "content": "hi"}])
    assert code_of(raised.value) == "auth"
