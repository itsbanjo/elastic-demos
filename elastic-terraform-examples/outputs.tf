output "elasticsearch_endpoint" {
  value = ec_deployment.example.elasticsearch.https_endpoint
}

output "kibana_endpoint" {
  value = ec_deployment.example.kibana.https_endpoint
}

output "elasticsearch_username" {
  value = ec_deployment.example.elasticsearch_username
}

output "elasticsearch_password" {
  value     = ec_deployment.example.elasticsearch_password
  sensitive = true
}
