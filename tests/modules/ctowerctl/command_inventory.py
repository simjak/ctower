"""Closed authored CLI handler inventory shared by boundary tests."""

from __future__ import annotations

from ctower_client.operations import CLI_OPERATIONS, SpoolPolicy
from ctowerctl import _credential_commands, _ruling_commands
from ctowerctl._attention_commands import mutation_command_names as attention_mutations
from ctowerctl._company_commands import mutation_command_names as company_mutations
from ctowerctl._company_commands import query_command_names as company_queries
from ctowerctl._digest_commands import query_command_names as digest_queries
from ctowerctl._dream_dispatch_commands import (
    mutation_command_names as dream_dispatch_mutations,
)
from ctowerctl._dream_dispatch_commands import query_command_names as dream_dispatch_queries
from ctowerctl._dream_lane_commands import mutation_command_names as dream_lane_mutations
from ctowerctl._inbox_commands import mutation_command_names as inbox_mutations
from ctowerctl._inbox_commands import query_command_names as inbox_queries
from ctowerctl._intake_commands import mutation_command_names as intake_mutations
from ctowerctl._knowledge_commands import mutation_command_names as knowledge_mutations
from ctowerctl._knowledge_commands import query_command_names as knowledge_queries
from ctowerctl._migration_commands import mutation_command_names as migration_mutations
from ctowerctl._migration_commands import query_command_names as migration_queries
from ctowerctl._migration_commands import refusal_command_names as migration_refusals
from ctowerctl._ops_commands import mutation_command_names as ops_mutations
from ctowerctl._ops_commands import query_command_names as ops_queries
from ctowerctl._pool_commands import mutation_command_names as pool_mutations
from ctowerctl._pool_commands import query_command_names as pool_queries
from ctowerctl._request_commands import mutation_command_names as request_mutations
from ctowerctl._request_commands import query_command_names as request_queries
from ctowerctl._session_commands import mutation_command_names as session_mutations
from ctowerctl._session_commands import query_command_names as session_queries
from ctowerctl._spawn_commands import mutation_command_names as spawn_mutations
from ctowerctl._spawn_commands import query_command_names as spawn_queries
from ctowerctl._synthetic_commands import mutation_command_names as synthetic_mutations
from ctowerctl._synthetic_commands import query_command_names as synthetic_queries
from ctowerctl._ticket_commands import mutation_command_names as ticket_mutations
from ctowerctl._ticket_commands import query_command_names as ticket_queries

__all__ = ["assert_explicit_handlers_cover_generated_operations"]

_FORBIDDEN_MUTATION_NAMES = frozenset(
    {
        "bootstrap first-tenant",
        "credential seat issue",
        "credential seat revoke",
        "dream-lane bind",
        "migration ctower-company-record import",
        "migration ctower-inbox import",
        "migration ctower-knowledge import",
        "migration ctower-project inventory",
        "migration ctower-project export",
        "migration ctower-project plan",
        "migration ctower-project import",
        "migration ctower-project reconcile",
        "migration ctower-project correction append",
        "migration ctower-project fence observe",
        "migration ctower-ruling import",
    }
)


def assert_explicit_handlers_cover_generated_operations() -> None:
    mutations = (
        ticket_mutations()
        | company_mutations()
        | ops_mutations()
        | synthetic_mutations()
        | migration_mutations()
        | intake_mutations()
        | inbox_mutations()
        | knowledge_mutations()
        | pool_mutations()
        | _credential_commands.mutation_command_names()
        | session_mutations()
        | attention_mutations()
        | dream_dispatch_mutations()
        | dream_lane_mutations()
        | (request_mutations() | _ruling_commands.mutation_command_names())
        | spawn_mutations()
    )
    queries = (
        ticket_queries()
        | company_queries()
        | ops_queries()
        | synthetic_queries()
        | migration_queries()
        | inbox_queries()
        | knowledge_queries()
        | pool_queries()
        | session_queries()
        | dream_dispatch_queries()
        | (digest_queries() | request_queries() | _ruling_commands.query_command_names())
        | spawn_queries()
    )
    refusals = migration_refusals()
    expected_mutations = {name for name, operation in CLI_OPERATIONS.items() if operation.mutation}
    expected_queries = {
        name
        for name, operation in CLI_OPERATIONS.items()
        if not operation.mutation and not operation.refusal_only
    }
    expected_refusals = {
        name for name, operation in CLI_OPERATIONS.items() if operation.refusal_only
    }
    forbidden = {
        name
        for name, operation in CLI_OPERATIONS.items()
        if operation.mutation and operation.spool_policy is SpoolPolicy.FORBIDDEN
    }

    assert mutations == expected_mutations - {"bootstrap first-tenant"}
    assert queries == expected_queries
    assert refusals == expected_refusals
    assert forbidden == _FORBIDDEN_MUTATION_NAMES
