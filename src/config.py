from dotenv import dotenv_values


def load_config(vars_path: str = "vars.env") -> dict:
    """Load configuration from a single vars.env file.
    
    Args:
        vars_path: Path to vars.env file containing all config, including secrets
    
    Returns:
        dict with keys: github_org, github_api_base_url, github_app_id,
        github_app_private_key_path, github_app_installation_id, webhook_secret
    
    Raises:
        ValueError: If any required variable is missing or empty
    """
    # Read file without mutating os.environ
    merged = dotenv_values(vars_path)
    
    # Required keys mapping from env var names to output key names
    required_keys = {
        'GITHUB_ORG': 'github_org',
        'GITHUB_API_BASE_URL': 'github_api_base_url',
        'GITHUB_APP_ID': 'github_app_id',
        'GITHUB_APP_PRIVATE_KEY_PATH': 'github_app_private_key_path',
        'GITHUB_APP_INSTALLATION_ID': 'github_app_installation_id',
        'MY_GITHUB_SECRET': 'webhook_secret',
    }
    
    # Check all required keys are present and non-empty
    for env_key, config_key in required_keys.items():
        if env_key not in merged or not merged[env_key]:
            raise ValueError(f"Missing required variable: {env_key}")
    
    # Build output dict with snake_case keys
    return {
        'github_org': merged['GITHUB_ORG'],
        'github_api_base_url': merged['GITHUB_API_BASE_URL'],
        'github_app_id': merged['GITHUB_APP_ID'],
        'github_app_private_key_path': merged['GITHUB_APP_PRIVATE_KEY_PATH'],
        'github_app_installation_id': merged['GITHUB_APP_INSTALLATION_ID'],
        'webhook_secret': merged['MY_GITHUB_SECRET'],
    }
