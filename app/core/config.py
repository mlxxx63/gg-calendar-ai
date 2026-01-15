from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    APP_SECRET_KEY: str

    FRONTEND_ORIGIN: str = "http://localhost:5173"

    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"

settings = Settings()
