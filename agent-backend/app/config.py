"""Configuration for qPTM Agent Backend.

Loads settings from environment variables / .env file.

Local datasets under data/ are organized by PTM research aspect
(see data/README.md), not by database name.
"""

from pydantic_settings import BaseSettings
from pathlib import Path


_DATA_ROOT = Path(__file__).parent.parent / "data"


class Settings(BaseSettings):
    # LLM API (OpenCode Go — OpenAI-compatible; env names kept for compatibility)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://opencode.ai/zen/go/v1"
    deepseek_model: str = "deepseek-v4-flash"

    # qPTM REST API (PHP backend — deployed at /api/ on the qPTM web server)
    qptm_api_base_url: str = "https://qptm3.omicsbio.info/api"

    # External database APIs
    uniprot_api_base_url: str = "https://rest.uniprot.org"
    iptmnet_api_base_url: str = "https://research.bioinformatics.udel.edu/iptmnet/api"
    activedriver_api_base_url: str = "https://activedriverdb.org"
    string_api_base_url: str = "https://cn.string-db.org/api"
    biogrid_api_base_url: str = "https://webservice.thebiogrid.org"
    biogrid_access_key: str = ""
    intact_api_base_url: str = (
        "https://www.ebi.ac.uk/Tools/webservices/psicquic/intact/webservices/current/search"
    )
    reactome_api_base_url: str = "https://reactome.org/ContentService"
    kegg_api_base_url: str = "https://rest.kegg.jp"
    interpro_api_base_url: str = "https://www.ebi.ac.uk/interpro/api"
    pubtator_api_base_url: str = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api"
    pathbank_data_dir: str = str(_DATA_ROOT / "pathways" / "PathBank")
    subcell_data_dir: str = str(_DATA_ROOT / "localization" / "SubCELL")
    # eKPI Quantitative matrices (per-site *.csv.gz; large — not copied into data/)
    ekpi_data_dir: str = "/var/www/html/ekpi"
    ekpi_final_result_dir: str = "/var/www/html/ekpi/final_result"

    # Local data root (aspect-classified PTM datasets)
    data_root: str = str(_DATA_ROOT)

    # Aspect → source directories (relative defaults under data/)
    # Stage 1 — WHO (writers / erasers)
    enzymes_data_dir: str = str(_DATA_ROOT / "enzymes")
    # Stage 3 WHERE + Stage 4 WHY (split by functional aspect)
    psp_data_dir: str = str(_DATA_ROOT / "regulation" / "PhosphoSitePlus")
    psp_enzymes_data_dir: str = str(_DATA_ROOT / "enzymes" / "PhosphoSitePlus")
    psp_disease_data_dir: str = str(_DATA_ROOT / "disease" / "PhosphositePlus")
    funcscore_data_dir: str = str(_DATA_ROOT / "regulation" / "Funcscore")
    ptmint_data_dir: str = str(_DATA_ROOT / "interactions" / "PTMint")
    ptmcode_data_dir: str = str(_DATA_ROOT / "interactions" / "PTMcode2")
    stability_data_dir: str = str(_DATA_ROOT / "stability" / "curated")
    ptmphase_data_dir: str = str(_DATA_ROOT / "phase_separation" / "ptmphase")
    dscope_data_dir: str = str(_DATA_ROOT / "phase_separation" / "dscope")
    dbptm_data_dir: str = str(_DATA_ROOT / "disease" / "dbptm")
    activedriver_data_dir: str = str(_DATA_ROOT / "disease" / "ActiveDriverDB")
    ptmd_data_dir: str = str(_DATA_ROOT / "disease" / "PTMD")
    cancerproteome_data_dir: str = str(_DATA_ROOT / "disease" / "CancerProteome")
    pmads_data_dir: str = str(_DATA_ROOT / "drug" / "PMADS")
    drugbank_data_dir: str = str(_DATA_ROOT / "drug" / "DrugBank")
    decryptm_data_dir: str = str(_DATA_ROOT / "drug" / "decryptM")
    proteomicsdb_api_base_url: str = "https://www.proteomicsdb.org"
    localization_data_dir: str = str(_DATA_ROOT / "localization")
    compartments_data_dir: str = str(_DATA_ROOT / "localization" / "COMPARTMENTS")
    inuloc_data_dir: str = str(_DATA_ROOT / "localization" / "iNuLoC")

    # Runtime (not scientific data)
    conversations_data_dir: str = str(_DATA_ROOT / "_runtime" / "conversations")

    # Server
    host: str = "0.0.0.0"
    port: int = 8100

    # CORS
    cors_origins: str = "http://localhost,http://qptm3.omicsbio.info,https://qptm3.omicsbio.info"

    # HTTP client defaults
    http_timeout_seconds: int = 60

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
