import os

from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions

DEFAULT_OPTIONS = OpenAIChatOptions(temperature=0.0)


def create_client(api_key: str, model: str, options: OpenAIChatOptions = DEFAULT_OPTIONS):
    """Create and return an OpenAIChatClient and options."""
    client = OpenAIChatClient(
        api_key=api_key,
        model=model,
    )
    return client, options
