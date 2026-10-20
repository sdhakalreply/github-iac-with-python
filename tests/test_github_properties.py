import json

import pytest
import responses

from src.github_properties import ensure_property_schema

URL = "https://api.github.com/orgs/my-org/properties/schema"

DEFINITIONS = [
    {"name": "jira-project-key", "type": "string"},
    {"name": "repo-category", "type": "multi_select", "allowed_values": ["service", "infra"]},
]


@responses.activate
def test_ensure_property_schema_sends_payload():
    responses.add(responses.PATCH, URL, json=[], status=200)
    ensure_property_schema("my-org", "ghs_abc123", DEFINITIONS, "https://api.github.com")
    body = json.loads(responses.calls[0].request.body)
    assert body["properties"][0] == {
        "property_name": "jira-project-key",
        "value_type": "string",
        "required": False,
    }
    assert body["properties"][1]["allowed_values"] == ["service", "infra"]


@responses.activate
def test_ensure_property_schema_no_definitions_makes_no_call():
    ensure_property_schema("my-org", "ghs_abc123", [], "https://api.github.com")
    assert len(responses.calls) == 0


@responses.activate
def test_ensure_property_schema_raises_on_error():
    responses.add(responses.PATCH, URL, json={"message": "Forbidden"}, status=403)
    with pytest.raises(RuntimeError, match="403"):
        ensure_property_schema("my-org", "ghs_abc123", DEFINITIONS, "https://api.github.com")


def test_select_type_needs_allowed_values():
    with pytest.raises(ValueError, match="allowed_values"):
        ensure_property_schema(
            "my-org", "ghs_abc123", [{"name": "x", "type": "multi_select"}], "https://api.github.com"
        )


def test_unknown_type_rejected():
    with pytest.raises(ValueError, match="type must be one of"):
        ensure_property_schema(
            "my-org", "ghs_abc123", [{"name": "x", "type": "number"}], "https://api.github.com"
        )
