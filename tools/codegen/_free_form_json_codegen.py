"""Render the authored recursive free-form JSON profile for both clients."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tools.codegen._json_integer_codegen import JsonIntegerProfile

__all__ = [
    "FreeFormJsonProfile",
    "has_free_form_additional_properties",
    "render_python_free_form_validator",
    "render_typescript_free_form_decoder",
    "require_free_form_json_profile",
]

_PROFILE_KEY = "x-ctower-free-form-json-profile"
_EXPECTED_PROFILE: Mapping[str, object] = {
    "containers": "recursive-arrays-and-objects",
    "duplicate-object-members": "last-member-wins",
    "fraction-exponent-negative-zero": "preserve-sign",
    "fraction-exponent-semantics": "finite-ieee-754-binary64",
    "integer-lexemes": "x-ctower-json-integer-profile",
    "nonfinite": "rejected",
    "overflow": "rejected",
    "trust": "opaque-until-component-schema-validation",
    "underflow": "preserve-binary64-signed-zero",
}


@dataclass(frozen=True, slots=True)
class FreeFormJsonProfile:
    """Exact immutable free-form JSON semantics consumed by both generators."""

    containers: str
    duplicate_object_members: str
    fraction_exponent_negative_zero: str
    fraction_exponent_semantics: str
    integer_lexemes: str
    nonfinite: str
    overflow: str
    trust: str
    underflow: str


def require_free_form_json_profile(document: Mapping[str, object]) -> FreeFormJsonProfile:
    """Fail generation unless the authored recursive JSON profile is exact."""

    if document.get(_PROFILE_KEY) != _EXPECTED_PROFILE:
        raise ValueError(f"{_PROFILE_KEY} must declare the exact supported JSON profile")
    return _supported_profile()


def _supported_profile() -> FreeFormJsonProfile:
    return FreeFormJsonProfile(
        containers="recursive-arrays-and-objects",
        duplicate_object_members="last-member-wins",
        fraction_exponent_negative_zero="preserve-sign",
        fraction_exponent_semantics="finite-ieee-754-binary64",
        integer_lexemes="x-ctower-json-integer-profile",
        nonfinite="rejected",
        overflow="rejected",
        trust="opaque-until-component-schema-validation",
        underflow="preserve-binary64-signed-zero",
    )


def has_free_form_additional_properties(schema: Mapping[str, object]) -> bool:
    """Return whether an object structurally selects the authored free-form profile."""

    if "additionalProperties" not in schema:
        return True
    additional = schema["additionalProperties"]
    return additional is True or (isinstance(additional, Mapping) and not additional)


def render_python_free_form_validator(
    profile: FreeFormJsonProfile,
    integer_profile: JsonIntegerProfile,
) -> str:
    """Render one private recursive Pydantic pre-validator."""

    _confirm_profile(profile)
    return f"""def _validate_free_form_json(value: object) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if type(value) is int:
        if {integer_profile.minimum} <= value <= {integer_profile.maximum}:
            return
        raise ValueError("free-form JSON integer is outside the lossless JSON range")
    if type(value) is float:
        if math.isfinite(value):
            return
        raise ValueError("free-form JSON number must be finite")
    if isinstance(value, list):
        for item in value:
            _validate_free_form_json(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("free-form JSON object keys must be strings")
            _validate_free_form_json(item)
        return
    raise ValueError("free-form JSON contains a non-JSON value")


def _validate_free_form_json_object(value: object) -> object:
    if not isinstance(value, dict):
        raise ValueError("free-form JSON object must be a dictionary")
    _validate_free_form_json(value)
    return value


_FreeFormJsonObject = Annotated[
    dict[str, object],
    BeforeValidator(_validate_free_form_json_object),
]"""


def render_typescript_free_form_decoder(profile: FreeFormJsonProfile) -> str:
    """Render one private raw-node materializer for recursive free-form JSON."""

    _confirm_profile(profile)
    return """function hasFreeFormAdditionalProperties(value: unknown): boolean {
  return (
    value === undefined ||
    value === true ||
    value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).length === 0
  );
}

const FREE_FORM_NUMBER_SCHEMA: SchemaObject = Object.freeze({});

function decodeUntyped(node: JsonNode, path: string): unknown {
  if (node === null || typeof node === "string" || typeof node === "boolean") return node;
  if (node.kind === "number") {
    return /[.eE]/u.test(node.raw)
      ? decodeNumber(FREE_FORM_NUMBER_SCHEMA, node, path)
      : decodeInteger(FREE_FORM_NUMBER_SCHEMA, node, path);
  }
  if (node.kind === "array") {
    return node.items.map((item, index) => decodeUntyped(item, `${path}[${index}]`));
  }
  const members = new Map<string, JsonNode>();
  for (const [name, member] of node.members) members.set(name, member);
  const result: Record<string, unknown> = {};
  for (const [name, member] of members) {
    Object.defineProperty(result, name, {
      configurable: true,
      enumerable: true,
      value: decodeUntyped(member, `${path}.${name}`),
      writable: true,
    });
  }
  return result;
}"""


def _confirm_profile(profile: FreeFormJsonProfile) -> None:
    if profile != _supported_profile():
        raise ValueError("free-form JSON renderer received an unsupported profile")
