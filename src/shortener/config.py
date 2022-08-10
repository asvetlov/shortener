from pydantic import BaseSettings, Field, RedisDsn


class Config(BaseSettings):
    http_port: int = Field(default=9000, env="HTTP_PORT")
    redis_url: RedisDsn = Field(env="REDIS_URL")
