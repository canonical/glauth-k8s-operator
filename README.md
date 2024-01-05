# GLAuth Kubernetes Charmed Operator

[![CharmHub Badge](https://charmhub.io/glauth-k8s/badge.svg)](https://charmhub.io/glauth-k8s)
![Python](https://img.shields.io/python/required-version-toml?label=Python&tomlFilePath=https://raw.githubusercontent.com/canonical/glauth-k8s-operator/main/pyproject.toml)
[![Juju](https://img.shields.io/badge/Juju%20-3.0+-%23E95420)](https://github.com/juju/juju)
![Ubuntu](https://img.shields.io/badge/Ubuntu-22.04-E95420?label=Ubuntu&logo=ubuntu&logoColor=white)
[![License](https://img.shields.io/github/license/canonical/glauth-k8s-operator?label=License)](https://github.com/canonical/glauth-k8s-operator/blob/main/LICENSE)

This repository holds the Juju Kubernetes charmed operator
for [GLAuth](https://github.com/glauth/glauth), an open-sourced LDAP server.

## Usage

The GLAuth charmed operator can be deployed using the following command:

```shell
$ juju deploy glauth-k8s --channel edge --trust
```

The GLAuth charmed operator uses
the [Charmed PostgreSQL K8s Operator](https://github.com/canonical/postgresql-k8s-operator)
as the backend:

```shell
$ juju deploy postgresql-k8s --channel stable --trust

$ juju integrate glauth-k8s postgresql-k8s
```

## Integrations

### `postgresql_client` Integration

The `glauth-k8s` charmed operator requires the integration with the
`postgres-k8s` charmed operator following the [`postgresql_client` interface
protocol](https://github.com/canonical/charm-relation-interfaces/tree/main/interfaces/postgresql_client/v0).

```shell
$ juju integrate glauth-k8s postgresql-k8s
```

### `ldap` Integration

The `glauth-k8s` charmed operator offers the `ldap` integration with any
LDAP client charmed operator following
the [`ldap` interface protocol](https://github.com/canonical/charm-relation-interfaces/tree/main/interfaces/ldap/v0).

```shell
$ juju integrate <ldap-client-charm>:ldap glauth-k8s:ldap
```

### `glauth_auxiliary` Integration

The `glauth-k8s` charmed operator provides the `glauth_auxiliary`
integration with
the [`glauth-utils` charmed operator](https://github.com/canonical/glauth-utils)
to deliver necessary auxiliary configurations.

```shell
$ juju integrate glauth-k8s glauth-utils
```

## Configurations

The `glauth-k8s` charmed operator offers the following charm configuration
options.

| Charm Config Option | Description                                                      | Example                                                 |
|:-------------------:|------------------------------------------------------------------|---------------------------------------------------------|
|      `base-dn`      | The portion of the DIT in which to search for matching entries   | `juju config <charm-app> base-dn="dc=glauth,dc=com"`    |
|     `hostname`      | The hostname of the LDAP server in `glauth-k8s` charmed operator | `juju config <charm-app> hostname="ldap.canonical.com"` |

> ⚠️ **NOTE**
>
> The `hostname` should **NOT** contain the ldap scheme (e.g. `ldap://`) and
> port.

## Contributing

Please refer to the [Contributing](CONTRIBUTING.md) for developer guidance.
Please see the [Juju SDK documentation](https://juju.is/docs/sdk) for more
information about developing and improving charms.

## Licence

The GLAuth Kubernetes Charmed Operator is free software, distributed under the
Apache Software License, version 2.0.
See [LICENSE](https://github.com/canonical/glauth-k8s-operator/blob/main/LICENSE)
for more information.
