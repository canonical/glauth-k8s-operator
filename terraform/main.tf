/**
 * # Terraform Module for GLAuth K8s Operator
 *
 * This is a Terraform module facilitating the deployment of the glauth-k8s
 * charm using the Juju Terraform provider.
 */

resource "juju_application" "glauth_k8s" {
  name        = var.app_name
  model_uuid  = var.model_uuid
  trust       = true
  config      = var.config
  constraints = var.constraints
  units       = var.units

  charm {
    name     = "glauth-k8s"
    base     = var.base
    channel  = var.channel
    revision = var.revision
  }
}
