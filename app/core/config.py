from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SALT: str
    DEFAULT_PLAYER: str | None = None
    DATABASE_URL: str
    RENDER: bool = False
    ERROR_CODES_FILE: str = "app/error_codes.json"
    PRIORITY_ACCOUNT: str
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
