# Elastic Cloud Terraform Provider — Complete Tutorial

> **`elastic/ec` · Terraform Registry · Latest**
> A complete hands-on guide to provisioning, configuring, and managing Elastic Cloud deployments and Serverless projects as code.

![Provider](https://img.shields.io/badge/Provider-elastic%2Fec-00bfb3?style=flat-square)
![Terraform](https://img.shields.io/badge/Terraform-%E2%89%A5%201.2.7-7b42bc?style=flat-square)
![Supports](https://img.shields.io/badge/Supports-ESS%20%C2%B7%20ECE%20%C2%B7%20Serverless-fec514?style=flat-square)

---

## Table of Contents

| # | Section |
|---|---------|
| 01 | [Overview & Providers](#01-overview--providers) |
| 02 | [Prerequisites](#02-prerequisites) |
| 03 | [Provider Setup & Authentication](#03-provider-setup--authentication) |
| 04 | [Your First Deployment](#04-your-first-deployment) |
| 05 | [Topology & Sizing](#05-topology--sizing) |
| 06 | [Autoscaling](#06-autoscaling) |
| 07 | [Serverless Projects](#07-serverless-projects) |
| 08 | [Traffic Filters](#08-traffic-filters) |
| 09 | [Remote Clusters (CCS/CCR)](#09-remote-clusters-ccsccr) |
| 10 | [Combining with Elastic Stack Provider](#10-combining-with-elastic-stack-provider) |
| 11 | [State Management & Import](#11-state-management--import) |
| 12 | [Resource Quick Reference](#12-resource-quick-reference) |
| A | [Appendix: Discover Templates via API](#appendix-discover-templates--instance-configs-via-api) |

---

## 01 Overview & Providers

Elastic publishes two complementary Terraform providers. Together they give you full Infrastructure-as-Code coverage of both the Elastic Cloud control plane and the Elastic Stack itself.

| Provider | Purpose |
|----------|---------|
| ☁️ **`elastic/ec`** | Manages Elastic Cloud infrastructure — deployments, serverless projects, traffic filters, remote clusters. Talks to the Elastic Cloud API. |
| 🔍 **`elastic/elasticstack`** | Configures the Elastic Stack itself — index templates, ILM policies, users, roles, ingest pipelines, dashboards. Works on-prem or on cloud. |

This tutorial focuses on `elastic/ec`. [Section 10](#10-combining-with-elastic-stack-provider) shows how to chain both providers together for end-to-end deployments.

> **ℹ️ Supported Environments**
> The `elastic/ec` provider supports Elasticsearch Service (ESS), Elastic Cloud Enterprise (ECE), Elasticsearch Service Private (ESSP), and Elastic Serverless projects.

---

## 02 Prerequisites

| Requirement | Detail |
|-------------|--------|
| ⚙️ **Terraform CLI** | Version `1.2.7` or higher. Earlier versions have known bugs with this provider. |
| 🔑 **Elastic Cloud Account** | An active account at [cloud.elastic.co](https://cloud.elastic.co). A free trial is available. |
| 🗝️ **API Key** | An Elastic Cloud **organisation-level** API key — not a cluster API key. |

### Generating an API Key

**Step 1 — Log in**

Navigate to `https://cloud.elastic.co/login` and sign in.

**Step 2 — Open API Keys**

In the left menu, choose **Features → API keys**. Click **Generate API key**. Assign the `Cloud resource access` role only — see [security note](#api-key-role-guidance) below.

**Step 3 — Export**

Copy the key immediately — it will not be shown again. Export it as an environment variable:

```bash
export EC_API_KEY="your-api-key-here"
```

#### API Key Role Guidance

For Terraform use the `elastic/ec` provider only needs **`Cloud resource access`**. Never assign `Organization owner` or `Billing admin` — they are unnecessary and increase blast radius if the key is leaked.

---

## 03 Provider Setup & Authentication

Create a `versions.tf` file to declare the provider and pin its version.

```hcl
# versions.tf
terraform {
  required_version = ">= 1.2.7"

  required_providers {
    ec = {
      source  = "elastic/ec"
      version = "~> 0.11"  # pin to latest minor
    }
  }
}

# Provider reads EC_API_KEY from environment automatically
provider "ec" {}
```

> **⚠️ Never Hard-Code Credentials**
> Do not put API keys directly in `.tf` files. Use the `EC_API_KEY` environment variable or a secrets manager like HashiCorp Vault.

### Provider Configuration Options

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `apikey` | String (sensitive) | — | API key. Recommended auth method. Set via `EC_API_KEY` env var. |
| `endpoint` | String | `https://api.elastic-cloud.com` | Override for ECE or private installations. |
| `username` | String | — | Username for ECE / ESSP (not for public ESS). |
| `password` | String (sensitive) | — | Password for ECE / ESSP. |
| `insecure` | Boolean | `false` | Skip TLS validation. Only for internal/dev ECE. |
| `timeout` | String | `1m` | Per-HTTP-call timeout. Increase for large deployments. |
| `verbose` | Boolean | `false` | Write HTTP requests to `request.log` for debugging. |

### ECE / On-Prem Configuration

```hcl
# provider.tf (ECE)
provider "ec" {
  endpoint = "https://ece.mycompany.internal:12443"
  apikey   = var.ec_api_key
  insecure = true  # only for self-signed certs in dev
}
```

Initialise the provider:

```bash
terraform init
```

---

## 04 Your First Deployment

The `ec_deployment` resource creates a full Elastic Stack deployment. The `ec_stack` data source dynamically resolves the latest available stack version.

```hcl
# main.tf

# Look up the latest available stack version for this region
data "ec_stack" "latest" {
  version_regex = "latest"
  region        = "azure-australiaeast"
}

# Minimal deployment: Elasticsearch + Kibana
resource "ec_deployment" "example" {
  name                   = "my-first-deployment"
  region                 = "azure-australiaeast"
  version                = data.ec_stack.latest.version
  deployment_template_id = "azure-general-purpose"  # see Appendix for discovery

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
```

> **⚠️ Template & Instance Config IDs change over time.** Elastic marks older hardware profiles as `legacy` — Terraform accepts them at plan time but fails at apply. Always use the [Appendix discovery commands](#appendix-discover-templates--instance-configs-via-api) to get live valid IDs for your region before writing config.

### Key Deployment Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `region` | ✅ Yes | Cloud region code. See [Appendix](#step-3--region-codes-quick-reference) for full list. ECE uses `ece-region`. |
| `version` | ✅ Yes | Stack version string. Use `data.ec_stack.latest.version` for auto-latest. |
| `deployment_template_id` | ✅ Yes | Template ID. Must be non-legacy. Discover via API — see Appendix. |
| `name` | No | Human-readable deployment name. |
| `alias` | No | Shortname affecting resource URLs. Set `""` to disable. |
| `tags` | No | Map of string tags applied to the deployment. |

### Outputs — Capturing Connection Details

```hcl
# outputs.tf
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
```

```bash
terraform apply
terraform output elasticsearch_endpoint
terraform output -raw elasticsearch_password
```

---

## 05 Topology & Sizing

From provider `v0.6.0` onward, the `elasticsearch` block uses **attribute syntax** (`= {...}` not block syntax) and each data tier is configured separately.

Available tiers: `hot` · `warm` · `cold` · `frozen` · `coordinating` · `ml` · `master`

```hcl
# main.tf — hot-warm architecture
resource "ec_deployment" "hot_warm" {
  name                   = "hot-warm-logging"
  region                 = "azure-australiaeast"
  version                = data.ec_stack.latest.version
  deployment_template_id = "azure-general-purpose"

  elasticsearch = {
    # Hot tier: recent/active data
    hot = {
      instance_configuration_id = "azure.es.datahot.ddv4"
      size                      = "8g"
      size_resource             = "memory"
      zone_count                = 2
      autoscaling               = {}
    }

    # Warm tier: older, less-queried data
    warm = {
      instance_configuration_id = "azure.es.datawarm.edsv4"
      size                      = "4g"
      size_resource             = "memory"
      zone_count                = 1
      autoscaling               = {}
    }

    # Cold tier: archived, infrequent access
    cold = {
      instance_configuration_id = "azure.es.datacold.edsv4"
      size                      = "2g"
      size_resource             = "memory"
      zone_count                = 1
      autoscaling               = {}
    }
  }

  kibana = {
    instance_configuration_id = "azure.kibana.fsv2"
    topology = {
      size       = "2g"
      zone_count = 1
    }
  }

  integrations_server = {
    instance_configuration_id = "azure.integrationsserver.fsv2"
  }
}
```

### Tier Size Reference

| Size Value | Memory | Typical Use |
|------------|--------|-------------|
| `"1g"` | 1 GB | Dev / testing |
| `"2g"` | 2 GB | Small production, Kibana |
| `"4g"` | 4 GB | Warm/cold tiers, light workloads |
| `"8g"` | 8 GB | Standard hot tier |
| `"16g"` | 16 GB | Heavy search, analytics |
| `"32g"` | 32 GB | Large clusters, ML nodes |
| `"64g"` | 64 GB | Memory-intensive / ML |

> **ℹ️ Dedicated Masters**
> The provider automatically adds a dedicated master tier when data node count exceeds the template threshold (default: 6), and removes it when not needed. Configure explicitly with `master = { ... }` if you need to override.

---

## 06 Autoscaling

Autoscaling allows Elastic Cloud to dynamically adjust tier capacity based on disk usage and ML demand. Each autoscaleable tier requires an `autoscaling = {}` block with optional min/max bounds.

```hcl
# main.tf — autoscaling with bounds
resource "ec_deployment" "autoscaled" {
  name                   = "autoscaled-cluster"
  region                 = "azure-australiaeast"
  version                = data.ec_stack.latest.version
  deployment_template_id = "azure-general-purpose"

  elasticsearch = {
    hot = {
      instance_configuration_id = "azure.es.datahot.ddv4"
      autoscaling = {
        autoscale      = true
        min_size       = "8g"
        max_size       = "64g"
        min_zone_count = 2
        max_zone_count = 3
      }
    }

    ml = {
      instance_configuration_id = "azure.es.ml.fsv2"
      autoscaling = {
        autoscale = true
        min_size  = "0g"   # start at zero when no ML jobs
        max_size  = "32g"
      }
    }
  }

  kibana = {}
}
```

> **⚠️ ML Tier Drift**
> When autoscaling is enabled, **all autoscaleable topology elements must be explicitly defined** in the `elasticsearch` block. Omitting the `ml` block will cause persistent plan diffs on every `terraform plan`.

---

## 07 Serverless Projects

The provider supports three Serverless project types. Serverless projects are fully managed — no topology or sizing to configure.

| Resource | Description |
|----------|-------------|
| `ec_elasticsearch_project` | Serverless Elasticsearch — search and analytics workloads |
| `ec_observability_project` | Serverless Observability — logs, metrics, and APM |
| `ec_security_project` | Serverless Security — SIEM and threat detection |

```hcl
# serverless.tf

# Serverless Elasticsearch project
resource "ec_elasticsearch_project" "search" {
  name      = "my-search-project"
  region_id = "azure-australiaeast"
}

# Serverless Observability project
resource "ec_observability_project" "obs" {
  name      = "platform-observability"
  region_id = "azure-australiaeast"
}

# Serverless Security project
resource "ec_security_project" "siem" {
  name      = "security-operations"
  region_id = "azure-australiaeast"
}

# Output serverless endpoint
output "search_endpoint" {
  value = ec_elasticsearch_project.search.endpoints.elasticsearch
}
```

---

## 08 Traffic Filters

Traffic filters restrict inbound access to specific IP ranges or VPC endpoints. The provider manages the **full set of rules** for a deployment — do not mix `traffic_filter` on `ec_deployment` with `ec_deployment_traffic_filter_association` for the same deployment.

```hcl
# traffic.tf

# IP-based traffic filter
resource "ec_deployment_traffic_filter" "office" {
  name   = "office-ips"
  region = "azure-australiaeast"
  type   = "ip"

  rule = [{
    source      = "203.0.113.0/24"
    description = "Sydney Office"
  }, {
    source      = "198.51.100.0/24"
    description = "Auckland Office"
  }]
}

# Attach filter to deployment
resource "ec_deployment" "secure" {
  name                   = "filtered-deployment"
  region                 = "azure-australiaeast"
  version                = data.ec_stack.latest.version
  deployment_template_id = "azure-general-purpose"

  traffic_filter = [
    ec_deployment_traffic_filter.office.id
  ]

  elasticsearch = { hot = { autoscaling = {} } }
  kibana        = {}
}
```

### Azure Private Link Traffic Filter

```hcl
# privatelink.tf
resource "ec_deployment_traffic_filter" "privatelink" {
  name   = "azure-privatelink"
  region = "azure-australiaeast"
  type   = "azure_private_endpoint"

  rule = [{
    azure_endpoint_name = "my-private-endpoint"
    azure_endpoint_guid = "00000000-0000-0000-0000-000000000000"
    description         = "Production VNet Endpoint"
  }]
}
```

---

## 09 Remote Clusters (CCS/CCR)

Cross-Cluster Search and Cross-Cluster Replication require remote cluster relationships defined directly on `ec_deployment`.

```hcl
# remote_clusters.tf

# Primary cluster
resource "ec_deployment" "primary" {
  name                   = "primary-cluster"
  region                 = "azure-australiaeast"
  version                = data.ec_stack.latest.version
  deployment_template_id = "azure-general-purpose"
  elasticsearch          = { hot = { autoscaling = {} } }
  kibana                 = {}
}

# Secondary cluster with remote reference to primary
resource "ec_deployment" "secondary" {
  name                   = "secondary-cluster"
  region                 = "azure-australiaeast"
  version                = data.ec_stack.latest.version
  deployment_template_id = "azure-general-purpose"

  elasticsearch = {
    hot = { autoscaling = {} }

    remote_cluster = [{
      deployment_id = ec_deployment.primary.id
      alias         = ec_deployment.primary.name
      ref_id        = ec_deployment.primary.elasticsearch.ref_id
    }]
  }

  kibana = {}
}
```

---

## 10 Combining with Elastic Stack Provider

The `elastic/elasticstack` provider configures resources *inside* an Elasticsearch cluster — index templates, ILM policies, users, ingest pipelines, and more. Chain it with `elastic/ec` outputs for full end-to-end IaC.

```hcl
# versions.tf — both providers
terraform {
  required_version = ">= 1.2.7"
  required_providers {
    ec = {
      source  = "elastic/ec"
      version = "~> 0.11"
    }
    elasticstack = {
      source  = "elastic/elasticstack"
      version = "~> 0.11"
    }
  }
}

provider "ec" {}

# Wire the Stack provider using deployment outputs
provider "elasticstack" {
  elasticsearch {
    username  = ec_deployment.main.elasticsearch_username
    password  = ec_deployment.main.elasticsearch_password
    endpoints = [ec_deployment.main.elasticsearch.https_endpoint]
  }
}
```

```hcl
# stack_config.tf — ILM policy + component template

# 30-day ILM policy
resource "elasticstack_elasticsearch_index_lifecycle" "logs_policy" {
  name = "logs-30-day"

  hot = {
    min_age = "1d"
    rollover = {
      max_primary_shard_size = "50gb"
      max_age                = "7d"
    }
  }

  warm = {
    min_age    = "7d"
    shrink     = { number_of_shards = 1 }
    forcemerge = { max_num_segments = 1 }
  }

  delete = {
    min_age = "30d"
    delete  = {}
  }
}

# Component template
resource "elasticstack_elasticsearch_component_template" "logs_settings" {
  name = "logs-settings"

  template = {
    settings = jsonencode({
      index = {
        lifecycle        = { name = "logs-30-day" }
        number_of_shards = "3"
      }
    })
  }
}
```

---

## 11 State Management & Import

### Importing Existing Deployments

```bash
# Import by deployment ID (found in Elastic Cloud console URL)
terraform import 'ec_deployment.my_deployment' abc123def456

# After import, confirm state is clean
terraform plan
```

> **⚠️ Import Limitations**
> State import does not capture user passwords or secret tokens. After import, `terraform plan` may show changes for empty/zero-size attributes (e.g. cold tier with size 0). These can safely be applied — only state is updated, the live deployment does not change.

### Remote State (Recommended for Teams)

```hcl
# backend.tf — S3 remote state
terraform {
  backend "s3" {
    bucket         = "my-terraform-state"
    key            = "elastic/prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}
```

### Version Upgrades

```hcl
# Bump version to trigger rolling upgrade
resource "ec_deployment" "prod" {
  version = "8.18.0"  # change this value and run terraform apply
  # ...
}
```

---

## 12 Resource Quick Reference

### Resources

| Resource | Description |
|----------|-------------|
| `ec_deployment` | Elastic Cloud hosted deployment (Elasticsearch, Kibana, Fleet, etc.) |
| `ec_deployment_traffic_filter` | IP or VPC traffic filter ruleset |
| `ec_deployment_traffic_filter_association` | Associate an existing filter with a deployment |
| `ec_elasticsearch_project` | Serverless Elasticsearch project |
| `ec_observability_project` | Serverless Observability project |
| `ec_security_project` | Serverless Security project |
| `ec_snapshot_repository` | Snapshot repository (ECE only) |

### Data Sources

| Data Source | Description |
|-------------|-------------|
| `ec_stack` | Look up available stack versions by region and regex |
| `ec_deployment` | Read an existing deployment by ID or alias |
| `ec_deployments` | Search/filter multiple deployments |
| `ec_traffic_filter` | Read existing traffic filters |
| `ec_aws_privatelink_endpoint` | AWS PrivateLink endpoint details by region |
| `ec_azure_privatelink_endpoint` | Azure Private Link endpoint details by region |
| `ec_gcp_private_service_connect_endpoint` | GCP PSC endpoint details by region |

### Useful Commands

```bash
# Initialise / download providers
terraform init

# Preview changes without applying
terraform plan

# Apply changes
terraform apply

# Apply without interactive prompt (CI use)
terraform apply -auto-approve

# Destroy all managed resources
terraform destroy

# Enable debug logging
TF_LOG=DEBUG terraform apply 2>&1 | tee tf.log

# Enable verbose HTTP logging (writes request.log)
# Set verbose = true in provider block
terraform apply
```

---

## Appendix: Discover Templates & Instance Configs via API

> **Why This Matters**
> Template IDs and instance configuration IDs change between Elastic Cloud versions. The API marks older templates with `"legacy": "true"` in their metadata. Terraform accepts these values at plan time but **fails at apply time** with `deployments.elasticsearch_using_legacy_dt` errors. Always query live before writing config.

---

### Step 1 — List All Valid (Non-Legacy) Templates for a Region

Replace `REGION` with your target region code.

```bash
export REGION="azure-australiaeast"   # ← change this

curl -s -H "Authorization: ApiKey $EC_API_KEY" \
  "https://api.elastic-cloud.com/api/v1/deployments/templates?region=$REGION" \
  | jq '[.[] | select(.metadata != null)
    | select((.metadata
        | map(select(.key == "legacy" and .value == "true")))
        | length == 0)
    | {id: .id, name: .name}]'
```

**Example output for `azure-australiaeast`:**

```json
[
  { "id": "azure-storage-optimized",      "name": "Storage optimized" },
  { "id": "azure-cpu-optimized",          "name": "CPU optimized" },
  { "id": "azure-vector-search-optimized","name": "Vector Search optimized" },
  { "id": "azure-general-purpose",        "name": "General purpose" }
]
```

---

### Step 2 — Inspect Instance Configs for a Template

```bash
export REGION="azure-australiaeast"
export TEMPLATE_ID="azure-general-purpose"  # ← from Step 1

curl -s -H "Authorization: ApiKey $EC_API_KEY" \
  "https://api.elastic-cloud.com/api/v1/deployments/templates?region=$REGION" \
  | jq --arg t "$TEMPLATE_ID" \
    '.[] | select(.id == $t)
    | .instance_configurations[]
    | {id: .id, type: .instance_type, node_types: .node_types, sizes: .discrete_sizes.sizes}'
```

**Example output — `azure-general-purpose`:**

| `id` | `type` | `node_types` | Valid sizes (MB) |
|------|--------|--------------|-----------------|
| `azure.es.datahot.ddv4` | elasticsearch | master, data, ingest | 1024–61440 |
| `azure.es.datawarm.edsv4` | elasticsearch | data | 2048–61440 |
| `azure.es.datacold.edsv4` | elasticsearch | data | 2048–61440 |
| `azure.es.datafrozen.edsv4` | elasticsearch | data | 4096–61440 |
| `azure.es.master.fsv2` | elasticsearch | master | 1024–61440 |
| `azure.es.ml.fsv2` | elasticsearch | ml | 1024–61440 |
| `azure.kibana.fsv2` | kibana | — | 1024–8192 |
| `azure.integrationsserver.fsv2` | integrations_server | — | 1024–30720 |

---

### Step 3 — Region Codes Quick Reference

| Provider | Region | Region Code |
|----------|--------|-------------|
| ☁️ AWS | US East (N. Virginia) | `us-east-1` |
| ☁️ AWS | US West (Oregon) | `us-west-2` |
| ☁️ AWS | Asia Pacific (Sydney) | `ap-southeast-2` |
| ☁️ AWS | Asia Pacific (Singapore) | `ap-southeast-1` |
| 🔷 Azure | Australia East (NSW) | `azure-australiaeast` |
| 🔷 Azure | East US | `azure-eastus` |
| 🔷 Azure | West Europe | `azure-westeurope` |
| 🔷 Azure | Southeast Asia | `azure-southeastasia` |
| 🌐 GCP | US Central (Iowa) | `gcp-us-central1` |
| 🌐 GCP | Europe West (Frankfurt) | `gcp-europe-west3` |
| 🌐 GCP | Asia East (Taiwan) | `gcp-asia-east1` |
| 🌐 GCP | Australia Southeast | `gcp-australia-southeast1` |

---

### Step 4 — Generic Terraform Template

Use values from Steps 1–2 to fill in this template. Works for any hyperscaler and deployment type — swap the three `locals` values at the top.

```hcl
# ── Variables ──────────────────────────────────────────────────────────────
# Set these from the API discovery commands above

locals {
  region      = "azure-australiaeast"  # ← Step 3 region code
  template_id = "azure-general-purpose" # ← Step 1 non-legacy template ID

  # Instance config IDs from Step 2
  ic_hot    = "azure.es.datahot.ddv4"
  ic_kibana = "azure.kibana.fsv2"
  ic_fleet  = "azure.integrationsserver.fsv2"
}

# ── Stack version ───────────────────────────────────────────────────────────
data "ec_stack" "latest" {
  version_regex = "latest"
  region        = local.region
}

# ── Deployment ──────────────────────────────────────────────────────────────
resource "ec_deployment" "main" {
  name                   = "my-deployment"
  region                 = local.region
  version                = data.ec_stack.latest.version
  deployment_template_id = local.template_id

  elasticsearch = {
    hot = {
      instance_configuration_id = local.ic_hot
      size                      = "8g"
      size_resource             = "memory"
      zone_count                = 2
      autoscaling               = {}
    }
  }

  kibana = {
    instance_configuration_id = local.ic_kibana
    topology = {
      size          = "1g"
      size_resource = "memory"
      zone_count    = 1
    }
  }

  integrations_server = {
    instance_configuration_id = local.ic_fleet
    topology = {
      size          = "1g"
      size_resource = "memory"
      zone_count    = 1
    }
  }
}

# ── Outputs ─────────────────────────────────────────────────────────────────
output "elasticsearch_endpoint" {
  value = ec_deployment.main.elasticsearch.https_endpoint
}

output "kibana_endpoint" {
  value = ec_deployment.main.kibana.https_endpoint
}

output "elasticsearch_username" {
  value = ec_deployment.main.elasticsearch_username
}

output "elasticsearch_password" {
  value     = ec_deployment.main.elasticsearch_password
  sensitive = true
}
```

---

### One-Shot Discovery Script

Save as `discover.sh` and use it before writing any Terraform config.

```bash
#!/bin/bash
# Usage:
#   ./discover.sh <region>                    — lists non-legacy templates
#   ./discover.sh <region> <template_id>      — lists instance configs
#
# Example:
#   EC_API_KEY=xxx ./discover.sh azure-australiaeast
#   EC_API_KEY=xxx ./discover.sh azure-australiaeast azure-general-purpose

REGION=${1:?"Usage: $0 <region> [template_id]"}
TEMPLATE=${2:-}
BASE_URL="https://api.elastic-cloud.com/api/v1/deployments/templates?region=$REGION"

if [ -z "$TEMPLATE" ]; then
  echo "=== Non-legacy templates for $REGION ==="
  curl -s -H "Authorization: ApiKey $EC_API_KEY" "$BASE_URL" \
    | jq '[.[] | select(.metadata != null)
      | select((.metadata | map(select(.key=="legacy" and .value=="true"))) | length == 0)
      | {id: .id, name: .name}]'
else
  echo "=== Instance configs for $TEMPLATE in $REGION ==="
  curl -s -H "Authorization: ApiKey $EC_API_KEY" "$BASE_URL" \
    | jq --arg t "$TEMPLATE" \
      '.[] | select(.id == $t)
      | .instance_configurations[]
      | {id: .id, type: .instance_type, node_types: .node_types, sizes: .discrete_sizes.sizes}'
fi
```

```bash
chmod +x discover.sh

# List valid templates — Azure Australia East
EC_API_KEY=$EC_API_KEY ./discover.sh azure-australiaeast

# Get instance configs for a specific template
EC_API_KEY=$EC_API_KEY ./discover.sh azure-australiaeast azure-general-purpose

# AWS Sydney
EC_API_KEY=$EC_API_KEY ./discover.sh ap-southeast-2

# GCP Frankfurt
EC_API_KEY=$EC_API_KEY ./discover.sh gcp-europe-west3
```

> **💡 CI Pipeline Tip**
> Run `discover.sh` as a pre-flight check before `terraform plan` in your CI pipeline. If a template ID disappears from the non-legacy list, the pipeline will catch it before Terraform attempts a failing apply — saving you from mysterious `legacy_dt` errors.

---

## References

- [Terraform Registry — elastic/ec](https://registry.terraform.io/providers/elastic/ec/latest/docs)
- [GitHub — elastic/terraform-provider-ec](https://github.com/elastic/terraform-provider-ec)
- [Elastic Cloud REST API](https://www.elastic.co/guide/en/cloud/current/ec-restful-api.html)
- [Elastic Stack Terraform Provider](https://registry.terraform.io/providers/elastic/elasticstack/latest/docs)
- [Available regions & templates](https://www.elastic.co/guide/en/cloud/current/ec-regions-templates-instances.html)