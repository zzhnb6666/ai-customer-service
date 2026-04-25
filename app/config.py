from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Telegram
    telegram_bot_token: str = ""

    # WhatsApp
    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/customer_service"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"

    # Proxy
    proxy_url: str = ""

    # Conversation
    chat_history_ttl: int = 3600  # Redis TTL: 1 hour
    max_history_turns: int = 20   # Keep last 20 turns

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
