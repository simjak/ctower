"""Render one deterministic ASCII RFC 3986 URI predicate for both clients."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "AbsoluteUriProfile",
    "render_python_uri_validator",
    "render_typescript_uri_validator",
    "require_absolute_uri_profile",
]

_PROFILE_KEY = "x-ctower-absolute-uri-profile"
_EXPECTED_PROFILE: Mapping[str, object] = {
    "characters": "ascii-rfc3986",
    "fragment": "allowed",
    "grammar": "rfc3986-uri-with-required-scheme",
    "http-authority": "required-with-nonempty-host",
    "normalization": "none-return-original",
    "percent-encoding": "complete-two-hex-digit-triplets",
    "raw-backslash": "rejected",
    "raw-whitespace-controls": "rejected",
}
_UNRESERVED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
_SUB_DELIMITERS = "!$&'()*+,;="
_HEX_DIGITS = "0123456789ABCDEFabcdef"


@dataclass(frozen=True, slots=True)
class AbsoluteUriProfile:
    """Exact immutable URI semantics consumed by both client generators."""

    characters: str
    fragment: str
    grammar: str
    http_authority: str
    normalization: str
    percent_encoding: str
    raw_backslash: str
    raw_whitespace_controls: str


def require_absolute_uri_profile(document: Mapping[str, object]) -> AbsoluteUriProfile:
    """Fail generation unless the authored URI profile is exact."""

    if document.get(_PROFILE_KEY) != _EXPECTED_PROFILE:
        raise ValueError(f"{_PROFILE_KEY} must declare the exact supported URI grammar")
    return AbsoluteUriProfile(
        characters="ascii-rfc3986",
        fragment="allowed",
        grammar="rfc3986-uri-with-required-scheme",
        http_authority="required-with-nonempty-host",
        normalization="none-return-original",
        percent_encoding="complete-two-hex-digit-triplets",
        raw_backslash="rejected",
        raw_whitespace_controls="rejected",
    )


def render_python_uri_validator(profile: AbsoluteUriProfile) -> str:
    """Render the generated Python predicate from shared grammar tables."""

    _confirm_profile(profile)
    return f"""_URI_UNRESERVED = frozenset({_UNRESERVED!r})
_URI_SUB_DELIMITERS = frozenset({_SUB_DELIMITERS!r})
_URI_HEX_DIGITS = frozenset({_HEX_DIGITS!r})
_URI_PCHAR = _URI_UNRESERVED | _URI_SUB_DELIMITERS | frozenset(":@")


def _is_absolute_uri(value: str) -> bool:
    if not value or any(ord(char) <= 32 or ord(char) >= 127 or char == "\\\\" for char in value):
        return False
    colon = value.find(":")
    if colon <= 0 or not _is_uri_scheme(value[:colon]):
        return False
    scheme = value[:colon]
    remainder = value[colon + 1:]
    fragment_at = remainder.find("#")
    if fragment_at >= 0:
        fragment = remainder[fragment_at + 1:]
        remainder = remainder[:fragment_at]
        if not _valid_uri_component(fragment, allow_slash=True, allow_question=True):
            return False
    query_at = remainder.find("?")
    if query_at >= 0:
        query = remainder[query_at + 1:]
        remainder = remainder[:query_at]
        if not _valid_uri_component(query, allow_slash=True, allow_question=True):
            return False
    has_authority = remainder.startswith("//")
    host = ""
    if has_authority:
        authority_and_path = remainder[2:]
        slash_at = authority_and_path.find("/")
        authority = authority_and_path if slash_at < 0 else authority_and_path[:slash_at]
        path = "" if slash_at < 0 else authority_and_path[slash_at:]
        valid_authority, host = _parse_uri_authority(authority)
        if not valid_authority:
            return False
    else:
        path = remainder
    if not _valid_uri_component(path, allow_slash=True, allow_question=False):
        return False
    return scheme.lower() not in {{"http", "https"}} or (has_authority and bool(host))


def _is_uri_scheme(value: str) -> bool:
    return (
        bool(value)
        and _ascii_alpha(value[0])
        and all(_ascii_alpha(char) or _ascii_digit(char) or char in "+-." for char in value[1:])
    )


def _valid_uri_component(value: str, *, allow_slash: bool, allow_question: bool) -> bool:
    allowed = _URI_PCHAR
    if allow_slash:
        allowed = allowed | frozenset("/")
    if allow_question:
        allowed = allowed | frozenset("?")
    return _valid_uri_token(value, allowed)


def _valid_uri_token(value: str, allowed: frozenset[str]) -> bool:
    index = 0
    while index < len(value):
        char = value[index]
        if char == "%":
            if (
                index + 2 >= len(value)
                or value[index + 1] not in _URI_HEX_DIGITS
                or value[index + 2] not in _URI_HEX_DIGITS
            ):
                return False
            index += 3
        elif char in allowed:
            index += 1
        else:
            return False
    return True


def _parse_uri_authority(value: str) -> tuple[bool, str]:
    if value.count("@") > 1:
        return False, ""
    if "@" in value:
        userinfo, host_port = value.rsplit("@", 1)
        if not _valid_uri_token(
            userinfo, _URI_UNRESERVED | _URI_SUB_DELIMITERS | frozenset(":")
        ):
            return False, ""
    else:
        host_port = value
    if host_port.startswith("["):
        close = host_port.find("]")
        if close < 0 or not _valid_ip_literal(host_port[1:close]):
            return False, ""
        suffix = host_port[close + 1:]
        if suffix and (not suffix.startswith(":") or not _ascii_digits(suffix[1:])):
            return False, ""
        return True, host_port[:close + 1]
    if "[" in host_port or "]" in host_port or host_port.count(":") > 1:
        return False, ""
    if ":" in host_port:
        host, port = host_port.rsplit(":", 1)
        if not _ascii_digits(port):
            return False, ""
    else:
        host = host_port
    if not _valid_uri_token(host, _URI_UNRESERVED | _URI_SUB_DELIMITERS):
        return False, ""
    return True, host


def _valid_ip_literal(value: str) -> bool:
    if len(value) >= 4 and value[0] in "vV":
        version, separator, address = value[1:].partition(".")
        allowed = _URI_UNRESERVED | _URI_SUB_DELIMITERS | frozenset(":")
        return (
            separator == "."
            and bool(version)
            and all(char in _URI_HEX_DIGITS for char in version)
            and bool(address)
            and all(char in allowed for char in address)
        )
    return _valid_ipv6(value)


def _valid_ipv6(value: str) -> bool:
    if not value or value.count("::") > 1:
        return False
    if "::" not in value:
        groups = _ipv6_side_groups(value, allow_ipv4=True)
        return groups == 8
    left, right = value.split("::", 1)
    left_groups = _ipv6_side_groups(left, allow_ipv4=False)
    right_groups = _ipv6_side_groups(right, allow_ipv4=True)
    return (
        left_groups is not None
        and right_groups is not None
        and left_groups + right_groups < 8
    )


def _ipv6_side_groups(value: str, *, allow_ipv4: bool) -> int | None:
    if not value:
        return 0
    parts = value.split(":")
    if any(not part for part in parts):
        return None
    count = 0
    for index, part in enumerate(parts):
        if "." in part:
            if not allow_ipv4 or index != len(parts) - 1 or not _valid_ipv4(part):
                return None
            count += 2
        elif len(part) > 4 or any(char not in _URI_HEX_DIGITS for char in part):
            return None
        else:
            count += 1
    return count


def _valid_ipv4(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 4 and all(
        _ascii_digits(part)
        and (len(part) == 1 or not part.startswith("0"))
        and int(part) <= 255
        for part in parts
    )


def _ascii_alpha(value: str) -> bool:
    return "A" <= value <= "Z" or "a" <= value <= "z"


def _ascii_digit(value: str) -> bool:
    return "0" <= value <= "9"


def _ascii_digits(value: str) -> bool:
    return bool(value) and all(_ascii_digit(char) for char in value)"""


def render_typescript_uri_validator(profile: AbsoluteUriProfile) -> str:
    """Render the generated TypeScript predicate from shared grammar tables."""

    _confirm_profile(profile)
    return f"""const URI_UNRESERVED = {_UNRESERVED!r};
const URI_SUB_DELIMITERS = {_SUB_DELIMITERS!r};
const URI_HEX_DIGITS = {_HEX_DIGITS!r};
const URI_PCHAR = URI_UNRESERVED + URI_SUB_DELIMITERS + ":@";

function isAbsoluteUri(value: string): boolean {{
  if (value.length === 0) return false;
  for (const char of value) {{
    const code = char.charCodeAt(0);
    if (code <= 32 || code >= 127 || char === "\\\\") return false;
  }}
  const colon = value.indexOf(":");
  if (colon <= 0 || !isUriScheme(value.slice(0, colon))) return false;
  const scheme = value.slice(0, colon);
  let remainder = value.slice(colon + 1);
  const fragmentAt = remainder.indexOf("#");
  if (fragmentAt >= 0) {{
    const fragment = remainder.slice(fragmentAt + 1);
    remainder = remainder.slice(0, fragmentAt);
    if (!validUriComponent(fragment, true, true)) return false;
  }}
  const queryAt = remainder.indexOf("?");
  if (queryAt >= 0) {{
    const query = remainder.slice(queryAt + 1);
    remainder = remainder.slice(0, queryAt);
    if (!validUriComponent(query, true, true)) return false;
  }}
  const hasAuthority = remainder.startsWith("//");
  let host = "";
  let path: string;
  if (hasAuthority) {{
    const authorityAndPath = remainder.slice(2);
    const slashAt = authorityAndPath.indexOf("/");
    const authority = slashAt < 0 ? authorityAndPath : authorityAndPath.slice(0, slashAt);
    path = slashAt < 0 ? "" : authorityAndPath.slice(slashAt);
    const parsed = parseUriAuthority(authority);
    if (!parsed[0]) return false;
    host = parsed[1];
  }} else {{
    path = remainder;
  }}
  if (!validUriComponent(path, true, false)) return false;
  const lowerScheme = scheme.toLowerCase();
  return lowerScheme !== "http" && lowerScheme !== "https" || hasAuthority && host.length > 0;
}}

function isUriScheme(value: string): boolean {{
  if (value.length === 0 || !asciiAlpha(value[0] ?? "")) return false;
  for (const char of value.slice(1)) {{
    if (!asciiAlpha(char) && !asciiDigit(char) && !"+-.".includes(char)) return false;
  }}
  return true;
}}

function validUriComponent(
  value: string,
  allowSlash: boolean,
  allowQuestion: boolean,
): boolean {{
  const allowed = URI_PCHAR + (allowSlash ? "/" : "") + (allowQuestion ? "?" : "");
  return validUriToken(value, allowed);
}}

function validUriToken(value: string, allowed: string): boolean {{
  let index = 0;
  while (index < value.length) {{
    const char = value[index] ?? "";
    if (char === "%") {{
      if (
        index + 2 >= value.length ||
        !URI_HEX_DIGITS.includes(value[index + 1] ?? "") ||
        !URI_HEX_DIGITS.includes(value[index + 2] ?? "")
      ) return false;
      index += 3;
    }} else if (allowed.includes(char)) {{
      index += 1;
    }} else {{
      return false;
    }}
  }}
  return true;
}}

function parseUriAuthority(value: string): readonly [boolean, string] {{
  if (value.split("@").length > 2) return [false, ""];
  let hostPort = value;
  const at = value.lastIndexOf("@");
  if (at >= 0) {{
    const userinfo = value.slice(0, at);
    hostPort = value.slice(at + 1);
    if (!validUriToken(userinfo, URI_UNRESERVED + URI_SUB_DELIMITERS + ":")) {{
      return [false, ""];
    }}
  }}
  if (hostPort.startsWith("[")) {{
    const close = hostPort.indexOf("]");
    if (close < 0 || !validIpLiteral(hostPort.slice(1, close))) return [false, ""];
    const suffix = hostPort.slice(close + 1);
    if (suffix.length > 0 && (!suffix.startsWith(":") || !asciiDigits(suffix.slice(1)))) {{
      return [false, ""];
    }}
    return [true, hostPort.slice(0, close + 1)];
  }}
  if (hostPort.includes("[") || hostPort.includes("]") || hostPort.split(":").length > 2) {{
    return [false, ""];
  }}
  let host = hostPort;
  const colon = hostPort.lastIndexOf(":");
  if (colon >= 0) {{
    host = hostPort.slice(0, colon);
    if (!asciiDigits(hostPort.slice(colon + 1))) return [false, ""];
  }}
  if (!validUriToken(host, URI_UNRESERVED + URI_SUB_DELIMITERS)) return [false, ""];
  return [true, host];
}}

function validIpLiteral(value: string): boolean {{
  if (value.length >= 4 && "vV".includes(value[0] ?? "")) {{
    const dot = value.indexOf(".");
    if (dot < 2) return false;
    const version = value.slice(1, dot);
    const address = value.slice(dot + 1);
    const allowed = URI_UNRESERVED + URI_SUB_DELIMITERS + ":";
    return (
      [...version].every((char) => URI_HEX_DIGITS.includes(char)) &&
      address.length > 0 &&
      [...address].every((char) => allowed.includes(char))
    );
  }}
  return validIpv6(value);
}}

function validIpv6(value: string): boolean {{
  if (value.length === 0 || value.split("::").length > 2) return false;
  if (!value.includes("::")) return ipv6SideGroups(value, true) === 8;
  const [left = "", right = ""] = value.split("::", 2);
  const leftGroups = ipv6SideGroups(left, false);
  const rightGroups = ipv6SideGroups(right, true);
  return leftGroups !== undefined && rightGroups !== undefined && leftGroups + rightGroups < 8;
}}

function ipv6SideGroups(value: string, allowIpv4: boolean): number | undefined {{
  if (value.length === 0) return 0;
  const parts = value.split(":");
  if (parts.some((part) => part.length === 0)) return undefined;
  let count = 0;
  for (const [index, part] of parts.entries()) {{
    if (part.includes(".")) {{
      if (!allowIpv4 || index !== parts.length - 1 || !validIpv4(part)) return undefined;
      count += 2;
    }} else if (
      part.length > 4 ||
      [...part].some((char) => !URI_HEX_DIGITS.includes(char))
    ) {{
      return undefined;
    }} else {{
      count += 1;
    }}
  }}
  return count;
}}

function validIpv4(value: string): boolean {{
  const parts = value.split(".");
  return parts.length === 4 && parts.every((part) =>
    asciiDigits(part) &&
    (part.length === 1 || !part.startsWith("0")) &&
    Number(part) <= 255
  );
}}

function asciiAlpha(value: string): boolean {{
  return value >= "A" && value <= "Z" || value >= "a" && value <= "z";
}}

function asciiDigit(value: string): boolean {{
  return value >= "0" && value <= "9";
}}

function asciiDigits(value: string): boolean {{
  return value.length > 0 && [...value].every(asciiDigit);
}}"""


def _confirm_profile(profile: AbsoluteUriProfile) -> None:
    if profile != require_absolute_uri_profile({_PROFILE_KEY: dict(_EXPECTED_PROFILE)}):
        raise ValueError("absolute URI renderer received an unsupported profile")
