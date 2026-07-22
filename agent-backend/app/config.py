"""Configuration for qPTM Agent Backend.

Loads settings from environment variables / .env file.
"""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # qPTM REST API (PHP backend — deployed at /api/ on the qPTM web server)
    qptm_api_base_url: str = "https://qptm3.omicsbio.info/api"

    # External database APIs
    uniprot_api_base_url: str = "https://rest.uniprot.org"
    iptmnet_api_base_url: str = "https://research.bioinformatics.udel.edu/iptmnet/api"

    # Local data directories (relative to agent-backend/)
    psp_data_dir: str = str(Path(__file__).parent.parent / "data" / "psp")
    dbptm_data_dir: str = str(Path(__file__).parent.parent / "data" / "dbptm")
    stability_data_dir: str = str(Path(__file__).parent.parent / "data" / "stability")
    ptmphase_data_dir: str = str(Path(__file__).parent.parent / "data" / "ptmphase")
    ptmint_data_dir: str = str(Path(__file__).parent.parent / "data" / "ptmint")

    # Server
    host: str = "0.0.0.0"
    port: int = 8100

    # CORS
    cors_origins: str = "http://localhost,http://qptm3.omicsbio.info"

    # HTTP client defaults
    http_timeout_seconds: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
