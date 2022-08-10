from pydantic import BaseSettings, Field, RedisDsn


class Config(BaseSettings):
    http_port: int = Field(default=8080, env="HTTP_PORT")
    redis_url: RedisDsn = Field(default="redis://redis", env="REDIS_URL")
