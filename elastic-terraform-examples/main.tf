data "ec_stack" "latest" {
  version_regex = "latest"
  region        = "azure-australiaeast"
}

resource "ec_deployment" "example" {
  name                   = "my-first-deployment"
  region                 = "azure-australiaeast"
  version                = data.ec_stack.latest.version
  deployment_template_id = "azure-general-purpose"

  elasticsearch = {
    hot = {
      instance_configuration_id = "azure.es.datahot.ddv4"
      size                      = "8g"
      size_resource             = "memory"
      zone_count                = 2
      autoscaling               = {}
    }
  }

  kibana = {
    instance_configuration_id = "azure.kibana.fsv2"
    topology = {
      size          = "1g"
      size_resource = "memory"
      zone_count    = 1
    }
  }
}