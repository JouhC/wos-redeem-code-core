from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SALT: str
    DEFAULT_PLAYER: str | None = None
    DB_FILE: str
    RENDER: bool = False
    ERROR_CODES_FILE: str = "app/error_codes.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
