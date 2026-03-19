# GLAuth Kubernetes Charm - Copilot Instructions

## Project Context
This is a [Juju](https://juju.is/) Kubernetes Charm for [GLAuth](https://github.com/glauth/glauth), written in Python using the [Operator Framework](https://github.com/canonical/operator). It manages an LDAP server on Kubernetes, integrating with PostgreSQL (backend) and various observability/ingress tools.

## Architecture & Patterns

### Core Components
- **Charm Entry Point**: `src/charm.py` defines `GLAuthCharm`. It orchestrates events but delegates logic to helper classes and libraries.
- **Configuration**: `src/configs.py` uses `dataclasses` (e.g., `DatabaseConfig`, `LdapsConfig`) to type-safe and structure configuration data derived from Juju config and relations.
- **Integrations**: `src/integrations.py` encapsulates business logic for relations (e.g., LDAP provider/requirer, certificates).
- **Status Management**: `src/utils.py` allows declarative status handling.
- **Kubernetes**: Uses `lightkube` for direct K8s resource management (e.g., ConfigMaps, StatefulSets) via `src/kubernetes_resource.py`.

### Status Handling Pattern
Prefer using the `@block_when` and `@wait_when` decorators from `src/utils.py` to gate charm execution based on preconditions.
*Example:*
```python
# src/charm.py
@wait_when(container_not_connected, service_not_ready)
@block_when(integration_not_exists(DATABASE_INTEGRATION_NAME), database_not_ready)
def _on_config_changed(self, event: ConfigChangedEvent) -> None:
    ...
```

### Configuration & State
- **Config Data**: Load configuration into structured objects (e.g., `ConfigFileData` in `configs.py`) before rendering templates.
- **Pebble**: Use `self.unit.get_container(WORKLOAD_CONTAINER)` to interact with the workload. Restart services only when necessary (check plan changes).

## Developer Workflows

### Testing Standards (CRITICAL)
**Note:** This repository is migrating test frameworks. You **MUST** follow these rules for all new or updated tests:

1.  **Unit Tests**: Use `ops.testing` (formerly Scenario).
    -   **DO NOT** use `harness` or `ops.testing.Harness` directly if `ops.testing` Context is available.
    -   Tests must be stateless and declarative.
    -   Location: `tests/unit/`

    *Example (`ops.testing`):*
    ```python
    from ops.testing import Context, State, Relation
    from charm import GLAuthCharm

    def test_pebble_ready():
        ctx = Context(GLAuthCharm)
        state = State(config={"log_level": "debug"})
        out = ctx.run(ctx.on.pebble_ready(container), state)
        assert out.unit_status == ActiveStatus()
    ```

2.  **Integration Tests**: Use `jubilant`.
    -   **DO NOT** use `pytest-operator` directly.
    -   Location: `tests/integration/`

### Build & Lint
-   **Formatting**: `tox -e fmt`
-   **Linting**: `tox -e lint`
-   **Unit Tests**: `tox -e unit`

## Coding Conventions
-   **Typing**: All code must be fully typed (Python type hints).
-   **Docstrings**: Use Google-style docstrings.
-   **Imports**: Sort imports using `isort` (enforced by `tox -e fmt`).
-   **Error Handling**: specific exceptions in `src/exceptions.py`. Catch them at the top level/hook handler if they shouldn't crash the charm.
-   **Constants**: Define string literals (relation names, file paths, ports) in `src/constants.py`.
