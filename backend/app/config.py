from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    google_api_key: str = ""
    database_url: str = "sqlite:///./lightplan.db"
    upload_dir: str = "./uploads"
    cors_origins: list[str] = ["http://localhost:5173"]
    claude_model: str = "claude-sonnet-4-20250514"
    gemini_model: str = "gemini-2.5-pro"
    max_upload_size_mb: int = 50
    basic_auth_user: str = ""
    basic_auth_pass: str = ""

    model_config = {"env_file": ".env", "protected_namespaces": ("settings_",)}


settings = Settings()
