# GLAuth Kubernetes Charmed Operator

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

TBD.

## Configurations

TBD.

## Actions

TBD.

## Contributing

Please refer to the [Contributing](CONTRIBUTING.md) for developer guidance.
Please see the [Juju SDK documentation](https://juju.is/docs/sdk) for more
information about developing and improving charms.

## Licence

The GLAuth Kubernetes Charmed Operator is free software, distributed under the
Apache Software License, version 2.0.
See [LICENSE](https://github.com/canonical/glauth-k8s-operator/blob/main/LICENSE)
for more information.
