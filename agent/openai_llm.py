"""OpenAI (Responses API) behind the Anthropic Messages interface the agents are written against.

`OpenAIClient().beta.messages.create(**request)` / `.messages.create` / `.beta.messages.stream` take the same
Anthropic-shaped request the Guide, Builder, Creator, LLM parser, solver agent and transcript rewriter already
send, call `client.responses.create`, and return a real `BetaMessage` (text and tool_use blocks, stop_reason,
usage), so no agent loop changes. Like agent/offline_llm.py it is a stand-in client; agent/llm_client.py picks it
when LLM_PROVIDER=openai (D-024).

Request mapping: system blocks → `instructions`; user text / base64 image → input_text / input_image; assistant
text → an assistant message, tool_use → function_call; tool_result → function_call_output (text and images, an
error marked in the text); tools → function tools (strict off: our schemas have optional fields); tool_choice
auto/any/tool → auto/required/function; output_config effort → reasoning.effort, format json_schema →
text.format; max_tokens → max_output_tokens. Anthropic-only fields (cache_control, betas, fallbacks, speed,
thinking) are dropped: OpenAI caches long prefixes by itself. Reasoning items are not carried between requests
(store=False, history is rebuilt from the Anthropic-shaped messages each time).

Models: a Claude id maps by family — opus → OPENAI_MODEL (default gpt-6.1-sol), sonnet → OPENAI_MID_MODEL
(gpt-6.1-terra), haiku → OPENAI_SMALL_MODEL (gpt-6-luna); any other id is sent as it is. The opus-mapped calls
go out at service_tier "ultrafast" when the model has it (gpt-6.1-sol, gpt-6-astra: same model, faster output;
measured 9.3 → 4.7 s per Guide turn); OPENAI_SERVICE_TIER sends another tier instead ("default" = standard speed). OpenAI errors are
re-raised as the matching anthropic error class, so the agents' and backend's existing handlers keep working."""

import itertools
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

import anthropic
import httpx2
import openai
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock, BetaUsage

MODELS = {"opus": ("OPENAI_MODEL", "gpt-6.1-sol"), "sonnet": ("OPENAI_MID_MODEL", "gpt-6.1-terra"),
          "haiku": ("OPENAI_SMALL_MODEL", "gpt-6-luna")}
ULTRAFAST = {"gpt-6.1-sol", "gpt-6-astra"}
DROPPED = {"cache_control", "betas", "fallbacks", "speed", "thinking", "metadata", "extra_headers", "timeout"}
STATUS_ERRORS = {400: anthropic.BadRequestError, 401: anthropic.AuthenticationError,
                 403: anthropic.PermissionDeniedError, 404: anthropic.NotFoundError, 409: anthropic.ConflictError,
                 422: anthropic.UnprocessableEntityError, 429: anthropic.RateLimitError}
REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/responses")  # for errors raised without one
_ids = itertools.count(1)


def openai_model(model: str) -> str:
    for family, (variable, default) in MODELS.items():
        if model.startswith("claude-") and family in model:
            return os.environ.get(variable, default)
    return model


def plain(block: object) -> dict:
    """A content block as a dict (the agents append SDK blocks from earlier responses to their history)."""
    return block if isinstance(block, dict) else block.model_dump(exclude_none=True)


def image_part(block: dict) -> dict:
    source = block["source"]
    url = source["url"] if source.get("type") == "url" else f"data:{source['media_type']};base64,{source['data']}"
    return {"type": "input_image", "image_url": url}


def result_output(block: dict) -> str | list[dict]:
    """A tool_result's content as function_call_output: a string, or text + image parts."""
    content = block.get("content", "")
    prefix = "Error: " if block.get("is_error") else ""
    if isinstance(content, str):
        return prefix + content
    parts = [{"type": "input_text", "text": prefix + part["text"]} if part["type"] == "text" else image_part(part)
             for part in map(plain, content) if part["type"] in ("text", "image")]
    if all(part["type"] == "input_text" for part in parts):
        return "\n".join(part["text"] for part in parts)
    return parts


def input_items(messages: list[dict]) -> list[dict]:
    items: list[dict] = []
    for message in messages:
        content = message["content"]
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else [plain(b) for b in content]
        if message["role"] == "assistant":
            for block in blocks:
                if block["type"] == "text" and block["text"]:
                    items.append({"role": "assistant", "content": block["text"]})
                elif block["type"] == "tool_use":
                    items.append({"type": "function_call", "call_id": block["id"], "name": block["name"],
                                  "arguments": json.dumps(block["input"], ensure_ascii=False)})
            continue
        parts = []
        for block in blocks:
            if block["type"] == "tool_result":
                items.append({"type": "function_call_output", "call_id": block["tool_use_id"],
                              "output": result_output(block)})
            elif block["type"] == "text":
                parts.append({"type": "input_text", "text": block["text"]})
            elif block["type"] == "image":
                parts.append(image_part(block))
        if parts:
            items.append({"role": "user", "content": parts})
    return items


def tool_choice(choice: dict | None) -> object:
    if not choice or choice.get("type") == "auto":
        return None
    if choice["type"] == "any":
        return "required"
    if choice["type"] == "tool":
        return {"type": "function", "name": choice["name"]}
    return "none" if choice["type"] == "none" else None


def openai_request(params: dict) -> dict:
    params = {key: value for key, value in params.items() if key not in DROPPED}
    system = params.pop("system", None)
    claude = params.pop("model")
    request: dict = {"model": openai_model(claude), "store": False, "input": input_items(params.pop("messages"))}
    if claude.startswith("claude-") and "opus" in claude:  # the big model's calls only
        tier = os.environ.get("OPENAI_SERVICE_TIER", "ultrafast" if request["model"] in ULTRAFAST else "")
        if tier:
            request["service_tier"] = tier
    if system:
        request["instructions"] = system if isinstance(system, str) else "\n\n".join(
            plain(block)["text"] for block in system)
    if "max_tokens" in params:
        request["max_output_tokens"] = params.pop("max_tokens")
    tools = [{"type": "function", "name": tool["name"], "description": tool.get("description", ""),
              "parameters": tool["input_schema"], "strict": False}
             for tool in params.pop("tools", None) or [] if "input_schema" in tool]
    if tools:
        request["tools"] = tools
        if (choice := tool_choice(params.pop("tool_choice", None))) is not None:
            request["tool_choice"] = choice
    params.pop("tool_choice", None)
    config = params.pop("output_config", None) or {}
    if config.get("effort"):
        request["reasoning"] = {"effort": config["effort"]}
    if (form := config.get("format")) and form.get("type") == "json_schema":
        request["text"] = {"format": {"type": "json_schema", "name": form.get("name", "output"),
                                      "schema": form["schema"], "strict": False}}
    return request


def anthropic_message(response: object, model: str) -> BetaMessage:
    content: list = []
    refused = False
    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if part.type == "output_text" and part.text:
                    content.append(BetaTextBlock(type="text", text=part.text))
                elif part.type == "refusal":
                    refused = True
                    content.append(BetaTextBlock(type="text", text=part.refusal))
        elif item.type == "function_call":
            try:
                arguments = json.loads(item.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            content.append(BetaToolUseBlock(type="tool_use", id=item.call_id, name=item.name, input=arguments))
    incomplete = getattr(response, "incomplete_details", None)
    if refused:
        stop = "refusal"
    elif incomplete is not None and getattr(incomplete, "reason", None) == "max_output_tokens":
        stop = "max_tokens"  # before tool_use: a call cut off mid-arguments must not run with {}
    elif any(block.type == "tool_use" for block in content):
        stop = "tool_use"
    else:
        stop = "end_turn"
    usage = response.usage
    cached = (getattr(usage.input_tokens_details, "cached_tokens", 0) or 0) if usage else 0
    return BetaMessage(
        id=getattr(response, "id", None) or f"msg_openai_{next(_ids)}", type="message", role="assistant",
        model=model, content=content, stop_reason=stop, stop_sequence=None,
        usage=BetaUsage(input_tokens=(usage.input_tokens - cached) if usage else 0,
                        output_tokens=usage.output_tokens if usage else 0,
                        cache_read_input_tokens=cached, cache_creation_input_tokens=0))


def anthropic_error(error: openai.OpenAIError) -> Exception:
    """The anthropic error class the agents and backend handle, for an OpenAI error."""
    if isinstance(error, openai.APIStatusError):
        kind = STATUS_ERRORS.get(error.status_code)
        if kind is None:
            kind = anthropic.InternalServerError if error.status_code >= 500 else anthropic.APIStatusError
        return kind(f"OpenAI: {error.message}", response=error.response, body=error.body)
    request = getattr(error, "request", None) or REQUEST
    if isinstance(error, openai.APITimeoutError):
        return anthropic.APITimeoutError(request=request)
    if isinstance(error, openai.APIConnectionError):
        return anthropic.APIConnectionError(message=f"OpenAI: {error}", request=request)
    return anthropic.APIError(f"OpenAI: {error}", request=request, body=None)


class Stream:
    """`with client.beta.messages.stream(**params) as stream`: Anthropic-like text events, then the message."""

    def __init__(self, events: Iterator, model: str) -> None:
        self.events, self.model, self.final = events, model, None

    def __iter__(self) -> Iterator[SimpleNamespace]:
        try:
            for event in self.events:
                if event.type == "response.output_text.delta":
                    yield SimpleNamespace(type="content_block_delta",
                                          delta=SimpleNamespace(type="text_delta", text=event.delta))
                elif event.type == "response.output_item.done" and event.item.type == "message":
                    yield SimpleNamespace(type="content_block_stop")
                elif event.type in ("response.completed", "response.incomplete"):
                    self.final = anthropic_message(event.response, self.model)
                elif event.type in ("response.failed", "error"):
                    detail = getattr(getattr(event, "response", None), "error", None) or event
                    raise anthropic.APIError(f"OpenAI: {detail}", request=REQUEST, body=None)
        except openai.OpenAIError as error:
            raise anthropic_error(error) from error

    def get_final_message(self) -> BetaMessage:
        if self.final is None:
            for _ in self:
                pass
        if self.final is None:
            raise anthropic.APIError("OpenAI: the stream ended without a response", request=REQUEST, body=None)
        return self.final


class Messages:
    def __init__(self, client: openai.OpenAI) -> None:
        self.client = client

    def create(self, **params) -> BetaMessage:
        model = params["model"]
        try:
            response = self.client.responses.create(**openai_request(params))
        except openai.OpenAIError as error:
            raise anthropic_error(error) from error
        return anthropic_message(response, model)

    @contextmanager
    def stream(self, **params) -> Iterator[Stream]:
        model = params["model"]
        try:
            events = self.client.responses.create(**openai_request(params), stream=True)
        except openai.OpenAIError as error:
            raise anthropic_error(error) from error
        with events:
            yield Stream(iter(events), model)


class MissingKey:
    """Stands in for openai.OpenAI when no key is set: every request fails as a 401, so the agents and backend
    report it like a wrong key (code "auth") instead of failing when the client is built."""

    def __init__(self, reason: openai.OpenAIError) -> None:
        self.reason = reason
        self.responses = self

    def create(self, **request) -> object:
        raise openai.AuthenticationError(f"no OpenAI API key: {self.reason}", body=None,
                                         response=httpx2.Response(401, request=REQUEST))


class OpenAIClient:
    """The Anthropic client surface the agents use (`messages`, `beta.messages`), served by OpenAI."""

    def __init__(self, max_retries: int | None = None, client: openai.OpenAI | None = None) -> None:
        try:
            self.openai = client or (openai.OpenAI(max_retries=max_retries) if max_retries is not None
                                     else openai.OpenAI())
        except openai.OpenAIError as error:  # no key: built anyway, the first request reports it
            self.openai = MissingKey(error)
        self.messages = Messages(self.openai)
        self.beta = SimpleNamespace(messages=self.messages)
