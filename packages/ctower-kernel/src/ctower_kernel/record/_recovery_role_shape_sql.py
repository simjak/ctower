"""Exact PostgreSQL catalog boundary for reusable recovery roles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, cast

import psycopg

__all__ = ["RecoveryRoleConfigurationError", "validate_recovery_role_shapes"]

_SANITIZED_ERROR = "recovery role configuration does not match the declared catalog shape"
_RECOVERY_BOUNDARY_RELATIONS = frozenset(
    {
        "backup_manifests",
        "backup_verification_receipts",
        "expected_source_inventory_entries",
        "expected_source_inventory_revisions",
        "installation_identities",
        "object_backfill_receipts",
        "object_erasure_intents",
        "object_erasure_tombstones",
        "object_upload_receipts",
        "record_anchor_receipts",
        "restore_enablement_receipts",
        "restore_finding_resolutions",
        "restore_findings",
        "restore_runs",
        "restore_steps",
    }
)


class RecoveryRoleConfigurationError(ValueError):
    """An existing recovery role cannot be proven safe for exact reuse."""

    MESSAGE: ClassVar[str] = _SANITIZED_ERROR

    def __init__(self) -> None:
        super().__init__(self.MESSAGE)


@dataclass(frozen=True, slots=True)
class _Grant:
    kind: str
    namespace: str
    object_name: str
    subobject_name: str
    privilege: str
    grantable: bool = False
    grantor: str = "ctower_admin"


@dataclass(frozen=True, slots=True)
class _RoleShape:
    name: str
    grants: frozenset[_Grant]
    can_login: bool = False
    inherits: bool = False
    creates_roles: bool = False
    creates_databases: bool = False
    replicates: bool = False
    bypasses_rls: bool = False
    superuser: bool = False
    connection_limit: int = -1
    has_password: bool = False
    has_valid_until: bool = False
    outgoing_memberships: frozenset[str] = frozenset()
    incoming_memberships: frozenset[str] = frozenset()
    has_settings: bool = False
    has_forbidden_cluster_authority: bool = False


def _table_grants(*entries: tuple[str, tuple[str, ...]]) -> frozenset[_Grant]:
    return frozenset(
        _Grant("relation", "public", relation, "", privilege)
        for relation, privileges in entries
        for privilege in privileges
    )


def _column_grants(
    relation: str,
    columns: tuple[str, ...],
    privilege: str,
) -> frozenset[_Grant]:
    return frozenset(_Grant("column", "public", relation, column, privilege) for column in columns)


_SCHEMA_USAGE = frozenset({_Grant("schema", "", "public", "", "USAGE")})
_ROLE_SHAPES = (
    _RoleShape(
        "ctower_object",
        _SCHEMA_USAGE
        | _table_grants(
            ("proof_objects", ("SELECT",)),
            ("object_upload_receipts", ("INSERT", "SELECT")),
            ("object_backfill_receipts", ("INSERT", "SELECT")),
            ("object_erasure_intents", ("INSERT", "SELECT")),
            ("object_erasure_tombstones", ("INSERT", "SELECT")),
        )
        | _column_grants(
            "proof_objects",
            (
                "ciphertext_sha256",
                "content",
                "external_verified_at",
                "key_reference",
                "key_version",
                "object_key",
                "object_version",
                "storage_state",
                "wrapped_key_sha256",
            ),
            "UPDATE",
        ),
    ),
    _RoleShape(
        "ctower_backup",
        _SCHEMA_USAGE
        | _table_grants(
            ("backup_manifests", ("INSERT", "SELECT")),
            ("backup_verification_receipts", ("INSERT", "SELECT")),
            ("proof_objects", ("SELECT",)),
            ("object_upload_receipts", ("SELECT",)),
            ("object_erasure_intents", ("SELECT",)),
            ("object_erasure_tombstones", ("SELECT",)),
            ("expected_source_inventory_revisions", ("SELECT",)),
            ("expected_source_inventory_entries", ("SELECT",)),
        ),
    ),
    _RoleShape(
        "ctower_anchor",
        _SCHEMA_USAGE
        | _table_grants(
            ("record_anchor_receipts", ("INSERT", "SELECT")),
            ("durability_acknowledgements", ("SELECT",)),
            ("durability_acceptance_confirmations", ("SELECT",)),
        ),
    ),
    _RoleShape(
        "ctower_restore",
        _SCHEMA_USAGE
        | _table_grants(
            ("installation_identities", ("INSERT", "SELECT")),
            ("expected_source_inventory_revisions", ("INSERT", "SELECT")),
            ("expected_source_inventory_entries", ("INSERT", "SELECT")),
            ("restore_steps", ("INSERT", "SELECT")),
            ("restore_findings", ("INSERT", "SELECT")),
            ("restore_finding_resolutions", ("INSERT", "SELECT")),
            ("restore_enablement_receipts", ("INSERT", "SELECT")),
            ("restore_runs", ("INSERT", "SELECT")),
            ("backup_manifests", ("SELECT",)),
            ("backup_verification_receipts", ("SELECT",)),
            ("record_anchor_receipts", ("SELECT",)),
            ("proof_objects", ("SELECT",)),
            ("object_upload_receipts", ("SELECT",)),
            ("object_erasure_intents", ("SELECT",)),
            ("object_erasure_tombstones", ("SELECT",)),
            ("events", ("SELECT",)),
            ("command_results", ("SELECT",)),
            ("durability_acknowledgements", ("SELECT",)),
            ("durability_acceptance_confirmations", ("SELECT",)),
        )
        | _column_grants(
            "restore_runs",
            ("completed_at", "report_sha256", "rto_seconds", "status"),
            "UPDATE",
        ),
    ),
)


def validate_recovery_role_shapes(
    connection: psycopg.Connection[dict[str, object]],
) -> None:
    """Reject every existing recovery role that is not one declared exact shape."""

    try:
        provisioned = _database_boundary_is_provisioned(connection)
        for shape in _ROLE_SHAPES:
            _validate_existing_role(connection, shape, provisioned=provisioned)
    except RecoveryRoleConfigurationError:
        raise
    except (KeyError, TypeError, ValueError, psycopg.Error):
        raise RecoveryRoleConfigurationError from None


def _database_boundary_is_provisioned(
    connection: psycopg.Connection[dict[str, object]],
) -> bool:
    rows = connection.execute(
        """
        SELECT relation.relname
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND relation.relname = ANY(%s)
          AND relation.relkind IN ('r', 'p')
        ORDER BY relation.relname
        """,
        (list(_RECOVERY_BOUNDARY_RELATIONS),),
    ).fetchall()
    present = frozenset(str(row["relname"]) for row in rows)
    if not present:
        return False
    if present == _RECOVERY_BOUNDARY_RELATIONS:
        return True
    raise RecoveryRoleConfigurationError


def _validate_existing_role(
    connection: psycopg.Connection[dict[str, object]],
    shape: _RoleShape,
    *,
    provisioned: bool,
) -> None:
    role = _role_attributes(connection, shape.name)
    if role is None:
        return
    role_id = cast(int, role["oid"])
    expected_grants = shape.grants if provisioned else frozenset()
    attributes_match = _attributes_match(role, shape)
    memberships = _membership_closures(connection, role_id)
    has_settings = _has_settings(connection, role_id)
    has_forbidden_cluster_authority = _has_forbidden_cluster_authority(connection, role_id)
    grants = _direct_grants(connection, role_id)
    if (
        not attributes_match
        or memberships != (shape.outgoing_memberships, shape.incoming_memberships)
        or has_settings is not shape.has_settings
        or has_forbidden_cluster_authority is not shape.has_forbidden_cluster_authority
        or grants != expected_grants
    ):
        raise RecoveryRoleConfigurationError


def _role_attributes(
    connection: psycopg.Connection[dict[str, object]],
    role_name: str,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT oid, rolcanlogin, rolinherit, rolcreaterole, rolcreatedb, rolreplication,
            rolbypassrls, rolsuper, rolconnlimit, rolpassword IS NOT NULL AS has_password,
            rolvaliduntil IS NOT NULL AS has_valid_until
        FROM pg_catalog.pg_authid
        WHERE rolname = %s
        """,
        (role_name,),
    ).fetchone()


def _attributes_match(role: dict[str, object], shape: _RoleShape) -> bool:
    actual = (
        bool(role["rolcanlogin"]),
        bool(role["rolinherit"]),
        bool(role["rolcreaterole"]),
        bool(role["rolcreatedb"]),
        bool(role["rolreplication"]),
        bool(role["rolbypassrls"]),
        bool(role["rolsuper"]),
        cast(int, role["rolconnlimit"]),
        bool(role["has_password"]),
        bool(role["has_valid_until"]),
    )
    expected = (
        shape.can_login,
        shape.inherits,
        shape.creates_roles,
        shape.creates_databases,
        shape.replicates,
        shape.bypasses_rls,
        shape.superuser,
        shape.connection_limit,
        shape.has_password,
        shape.has_valid_until,
    )
    return actual == expected


def _membership_closures(
    connection: psycopg.Connection[dict[str, object]],
    role_id: int,
) -> tuple[frozenset[str], frozenset[str]]:
    rows = connection.execute(
        """
        WITH RECURSIVE
        outgoing(roleid) AS (
            SELECT membership.roleid
            FROM pg_catalog.pg_auth_members AS membership
            WHERE membership.member = %s
            UNION
            SELECT membership.roleid
            FROM pg_catalog.pg_auth_members AS membership
            JOIN outgoing ON outgoing.roleid = membership.member
        ),
        incoming(member) AS (
            SELECT membership.member
            FROM pg_catalog.pg_auth_members AS membership
            WHERE membership.roleid = %s
            UNION
            SELECT membership.member
            FROM pg_catalog.pg_auth_members AS membership
            JOIN incoming ON incoming.member = membership.roleid
        )
        SELECT 'outgoing' AS direction, role.rolname
        FROM outgoing JOIN pg_catalog.pg_roles AS role ON role.oid = outgoing.roleid
        UNION ALL
        SELECT 'incoming' AS direction, role.rolname
        FROM incoming JOIN pg_catalog.pg_roles AS role ON role.oid = incoming.member
        ORDER BY direction, rolname
        """,
        (role_id, role_id),
    ).fetchall()
    outgoing = frozenset(str(row["rolname"]) for row in rows if row["direction"] == "outgoing")
    incoming = frozenset(str(row["rolname"]) for row in rows if row["direction"] == "incoming")
    return outgoing, incoming


def _has_settings(
    connection: psycopg.Connection[dict[str, object]],
    role_id: int,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM pg_catalog.pg_db_role_setting
            WHERE setrole = %s
            LIMIT 1
            """,
            (role_id,),
        ).fetchone()
        is not None
    )


def _has_forbidden_cluster_authority(
    connection: psycopg.Connection[dict[str, object]],
    role_id: int,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1
            FROM pg_catalog.pg_shdepend AS dependency
            WHERE dependency.refclassid = 'pg_catalog.pg_authid'::regclass
              AND dependency.refobjid = %s
              AND (
                  dependency.deptype = 'o'
                  OR (
                      dependency.deptype = 'a'
                      AND dependency.dbid <> (
                          SELECT database.oid
                          FROM pg_catalog.pg_database AS database
                          WHERE database.datname = current_database()
                      )
                  )
              )
            LIMIT 1
            """,
            (role_id,),
        ).fetchone()
        is not None
    )


def _direct_grants(
    connection: psycopg.Connection[dict[str, object]],
    role_id: int,
) -> frozenset[_Grant]:
    rows = connection.execute(_DIRECT_GRANTS_SQL, (role_id,) * 13).fetchall()
    return frozenset(
        _Grant(
            kind=str(row["kind"]),
            namespace=str(row["namespace"]),
            object_name=str(row["object_name"]),
            subobject_name=str(row["subobject_name"]),
            privilege=str(row["privilege"]),
            grantable=bool(row["grantable"]),
            grantor=str(row["grantor"]),
        )
        for row in rows
    )


_DIRECT_GRANTS_SQL = """
SELECT 'database' AS kind, '' AS namespace, database.datname AS object_name,
    '' AS subobject_name, grant_entry.privilege_type AS privilege,
    grant_entry.is_grantable AS grantable,
    pg_catalog.pg_get_userbyid(grant_entry.grantor) AS grantor
FROM pg_catalog.pg_database AS database
CROSS JOIN LATERAL pg_catalog.aclexplode(database.datacl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'schema', '', namespace.nspname, '', grant_entry.privilege_type,
    grant_entry.is_grantable, pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_namespace AS namespace
CROSS JOIN LATERAL pg_catalog.aclexplode(namespace.nspacl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'relation', namespace.nspname, relation.relname, '',
    grant_entry.privilege_type, grant_entry.is_grantable,
    pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(relation.relacl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'column', namespace.nspname, relation.relname, attribute.attname,
    grant_entry.privilege_type, grant_entry.is_grantable,
    pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_attribute AS attribute
JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(attribute.attacl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'routine', namespace.nspname, routine.oid::text, '',
    grant_entry.privilege_type, grant_entry.is_grantable,
    pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_proc AS routine
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(routine.proacl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'type', namespace.nspname, type_entry.oid::text, '',
    grant_entry.privilege_type, grant_entry.is_grantable,
    pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_type AS type_entry
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = type_entry.typnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(type_entry.typacl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'language', '', language.lanname, '', grant_entry.privilege_type,
    grant_entry.is_grantable, pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_language AS language
CROSS JOIN LATERAL pg_catalog.aclexplode(language.lanacl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'large_object', '', large_object.oid::text, '', grant_entry.privilege_type,
    grant_entry.is_grantable, pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_largeobject_metadata AS large_object
CROSS JOIN LATERAL pg_catalog.aclexplode(large_object.lomacl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'foreign_data_wrapper', '', wrapper.fdwname, '', grant_entry.privilege_type,
    grant_entry.is_grantable, pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_foreign_data_wrapper AS wrapper
CROSS JOIN LATERAL pg_catalog.aclexplode(wrapper.fdwacl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'foreign_server', '', server.srvname, '', grant_entry.privilege_type,
    grant_entry.is_grantable, pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_foreign_server AS server
CROSS JOIN LATERAL pg_catalog.aclexplode(server.srvacl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'tablespace', '', tablespace.spcname, '', grant_entry.privilege_type,
    grant_entry.is_grantable, pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_tablespace AS tablespace
CROSS JOIN LATERAL pg_catalog.aclexplode(tablespace.spcacl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'parameter', '', parameter.parname, '', grant_entry.privilege_type,
    grant_entry.is_grantable, pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_parameter_acl AS parameter
CROSS JOIN LATERAL pg_catalog.aclexplode(parameter.paracl) AS grant_entry
WHERE grant_entry.grantee = %s
UNION ALL
SELECT 'default', COALESCE(namespace.nspname, ''), owner.rolname,
    default_acl.defaclobjtype::text, grant_entry.privilege_type,
    grant_entry.is_grantable, pg_catalog.pg_get_userbyid(grant_entry.grantor)
FROM pg_catalog.pg_default_acl AS default_acl
JOIN pg_catalog.pg_roles AS owner ON owner.oid = default_acl.defaclrole
LEFT JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = default_acl.defaclnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(default_acl.defaclacl) AS grant_entry
WHERE grant_entry.grantee = %s
"""
