# Charmed GLAuth

## Description

This repository hosts the Charmed Kubernetes Operator for [GLAuth](https://github.com/glauth/glauth) -  an LDAP Authentication server written in golang. Currently the glauth-k8s operator only supports GLAuth deployments with Postgresql backend.
For more details, visit https://glauth.github.io/

## Usage

The GLAuth Operator can be deployed using the Juju command line as follows:

```bash
juju deploy postgresql-k8s --trust
juju deploy glauth-k8s --trust
juju integrate glauth-k8s postgresql-k8s
```

## Relations

### PostgreSQL

This charm requires a relation with [postgresql-k8s-operator](https://github.com/canonical/postgresql-k8s-operator).

### Ingress

The GLAuth Kubernetes Operator offers integration with the [traefik-k8s-operator](https://github.com/canonical/traefik-k8s-operator). The ingress is provided to the configurable HTTP API interface. Prometheus scraping is available through the HTTP API. 

If you have a traefik deployed and configured in the same model as glauth-k8s, to provide ingress to theAPI run:
```console
juju integrate traefik glauth-k8s:ingress
```

## Canonical Observability Stack

This charm offers integration with observability tools in the [Canonical Observability Stack](https://charmhub.io/topics/canonical-observability-stack).

### Prometheus

The GLAuth Kubernetes Operator offers integration with the [Prometheus](https://github.com/canonical/prometheus-k8s-operator) operator in COS.

If you have Prometheus deployed and configured in the same model as glauth-k8s, to provide metrics scraping capability to Prometheus run:
```console
juju integrate prometheus-k8s:metrics-endpoint glauth-k8s
```

### Loki

The GLAuth Kubernetes Operator offers integration with the [Loki](https://github.com/canonical/loki-k8s-operator) operator in COS.

If you have Loki deployed and configured in the same model as glauth-k8s, to provide labeled logs to Loki run:
```console
juju integrate glauth-k8s:logging loki-k8s
```

## Security
Security issues in IAM stack can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this charm following best practice guidelines, and [CONTRIBUTING.md](https://github.com/canonical/glauth-k8s/blob/main/CONTRIBUTING.md) for developer guidance.


## License

The Charmed GLAuth Operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](https://github.com/canonical/glauth-k8s/blob/main/LICENSE) for more information.