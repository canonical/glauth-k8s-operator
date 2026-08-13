# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "The Juju application name"
  value       = juju_application.glauth_k8s.name
}

output "requires" {
  description = "The Juju integrations that the charm requires"
  value = {
    pg-database   = "pg-database"
    ingress       = "ingress"
    ldaps-ingress = "ldaps-ingress"
    certificates  = "certificates"
    ldap-client   = "ldap-client"
    logging       = "logging"
  }
}

output "provides" {
  description = "The Juju integrations that the charm provides"
  value = {
    ldap              = "ldap"
    glauth-auxiliary  = "glauth-auxiliary"
    send-ca-cert      = "send-ca-cert"
    metrics-endpoint  = "metrics-endpoint"
    grafana-dashboard = "grafana-dashboard"
  }
}
