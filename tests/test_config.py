import pytest
from src.config import load_config


def test_load_config_reads_vars_file(tmp_path):
    vars_file = tmp_path / "vars.env"
    vars_file.write_text(
        "TARGET_ORG=my-org\n"
        "API_BASE_URL=https://api.github.com\n"
        "APP_ID=123\n"
        "APP_INSTALLATION_ID=456\n"
        "APP_PRIVATE_KEY_PATH=./key.pem\n"
        "WEBHOOK_SECRET=supersecret\n"
    )
    config = load_config(str(vars_file))
    assert config["github_org"] == "my-org"
    assert config["github_api_base_url"] == "https://api.github.com"
    assert config["github_app_id"] == "123"
    assert config["github_app_private_key_path"] == "./key.pem"
    assert config["github_app_installation_id"] == "456"
    assert config["webhook_secret"] == "supersecret"


def test_load_config_missing_var_raises(tmp_path):
    vars_file = tmp_path / "vars.env"
    vars_file.write_text("TARGET_ORG=my-org\nAPP_ID=123\n")  # missing API_BASE_URL
    with pytest.raises(ValueError, match="API_BASE_URL"):
        load_config(str(vars_file))
