from pydantic import BaseSettings, Field, RedisDsn


class Config(BaseSettings):
    http_host: str = Field(default="localhost", env="HTTP_HOST")
    http_port: int = Field(default=8080, env="HTTP_PORT")
    redis_url: RedisDsn = Field(default="redis://redis", env="REDIS_URL")
    prometheus_host: str = Field(default="localhost", env="PROMETHEUS_HOST")
    prometheus_port: int = Field(default=8081, env="PROMETHEUS_PORT")
