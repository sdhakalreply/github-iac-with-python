import pytest
from src.config import load_config


def test_load_config_reads_vars_file(tmp_path):
    vars_file = tmp_path / "vars.env"
    vars_file.write_text(
        "GITHUB_ORG=my-org\n"
        "GITHUB_API_BASE_URL=https://api.github.com\n"
        "GITHUB_APP_ID=123\n"
        "GITHUB_APP_PRIVATE_KEY_PATH=./key.pem\n"
        "GITHUB_APP_INSTALLATION_ID=456\n"
        "MY_GITHUB_SECRET=supersecret\n"
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
    vars_file.write_text("GITHUB_ORG=my-org\nGITHUB_APP_ID=123\n")  # missing GITHUB_API_BASE_URL
    with pytest.raises(ValueError, match="GITHUB_API_BASE_URL"):
        load_config(str(vars_file))
