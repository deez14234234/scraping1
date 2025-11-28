from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "News Monitor"
    ENV: str = "dev"
    PORT: int = 8000

    DATABASE_URL: str = "sqlite:///./data/news.db"

    USER_AGENT: str = "NewsMonitorBot/1.0"
    REQUEST_TIMEOUT: int = 15
    # Scraper-specific
    RATE_LIMIT_SECONDS: float = 0.5  # seconds to wait between requests (simple global throttle)
    REQUEST_RETRIES: int = 3
    BACKOFF_FACTOR: float = 0.5

    SCRAPE_INTERVAL_MIN: int = 15

    # SMTP / Email settings (optional)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 25
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_STARTTLS: bool = False
    SMTP_FROM: str = "noreply@nexnews.com"
    EMAIL_ENABLED: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
