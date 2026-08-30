from dataclasses import dataclass

from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from app.core.config import Settings


@dataclass(frozen=True)
class ModelResources:
    client: AsyncOpenAI
    model: OpenAIChatCompletionsModel


def build_model_resources(settings: Settings) -> ModelResources:
    api_key = (
        settings.deepseek_api_key.get_secret_value()
        if settings.deepseek_api_key is not None
        else "missing-deepseek-api-key"
    )
    client = AsyncOpenAI(api_key=api_key, base_url=settings.deepseek_base_url)
    return ModelResources(
        client=client,
        model=OpenAIChatCompletionsModel(
            model=settings.deepseek_model,
            openai_client=client,
        ),
    )
