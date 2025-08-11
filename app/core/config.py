from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SALT: str
    DEFAULT_PLAYER: str | None = None
    DB_FILE: str
    RENDER: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
