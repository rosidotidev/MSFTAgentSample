from agent_framework.openai import OpenAIChatCompletionClient, OpenAIChatCompletionOptions

DEFAULT_OPTIONS = OpenAIChatCompletionOptions(temperature=0.0)


def create_client(
    base_url: str,
    model: str,
    api_key: str = "none",
    options: OpenAIChatCompletionOptions = DEFAULT_OPTIONS,
):
    """Create and return an OpenAIChatCompletionClient for a local Foundry model."""
    client = OpenAIChatCompletionClient(
        base_url=base_url,
        model=model,
        api_key=api_key,
    )
    return client, options
