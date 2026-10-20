import logging

import requests

logger = logging.getLogger(__name__)

VALUE_TYPES = {"string", "single_select", "multi_select", "true_false"}


def validate_property_definitions(definitions: list) -> None:
    """Raise ValueError if a property definition is malformed."""
    for i, definition in enumerate(definitions):
        if not isinstance(definition, dict) or "name" not in definition:
            raise ValueError(f"Property definition {i}: missing 'name'")
        value_type = definition.get("type", "string")
        if value_type not in VALUE_TYPES:
            raise ValueError(
                f"Property definition '{definition['name']}': type must be one of {sorted(VALUE_TYPES)}"
            )
        if value_type in ("single_select", "multi_select") and not definition.get("allowed_values"):
            raise ValueError(
                f"Property definition '{definition['name']}': '{value_type}' needs 'allowed_values'"
            )


def ensure_property_schema(org: str, token: str, definitions: list, api_base_url: str) -> None:
    """Create or update the org's custom property schema from the yaml.

    PATCH on the schema endpoint is create-or-update, so reruns are safe.
    """
    if not definitions:
        return
    validate_property_definitions(definitions)

    payload = {"properties": []}
    for definition in definitions:
        item = {
            "property_name": definition["name"],
            "value_type": definition.get("type", "string"),
            "required": bool(definition.get("required", False)),
        }
        if definition.get("description"):
            item["description"] = definition["description"]
        if definition.get("allowed_values"):
            item["allowed_values"] = definition["allowed_values"]
        payload["properties"].append(item)

    logger.info("Ensuring %d custom propert(y/ies) in org '%s'", len(definitions), org)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        response = requests.patch(
            f"{api_base_url}/orgs/{org}/properties/schema",
            headers=headers,
            json=payload,
        )
    except requests.exceptions.RequestException as exc:
        logger.error("Could not reach GitHub while ensuring property schema: %s", exc)
        raise RuntimeError(f"Could not reach GitHub while ensuring property schema: {exc}")

    if response.status_code < 200 or response.status_code >= 300:
        logger.error(
            "Failed to ensure property schema: %s %s", response.status_code, response.text
        )
        raise RuntimeError(
            f"Failed to ensure property schema: {response.status_code} {response.text}"
        )
    logger.info("Property schema ensured in org '%s'", org)
