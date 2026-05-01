# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

A collection of independent Elastic Stack demo projects. Each subdirectory is a self-contained demo with its own dependencies and tooling. There is no root-level build system.

## Projects

### `terraform-examples/`
Terraform configurations using the `elastic/ec` and `elastic/elasticstack` providers to provision Elastic Cloud deployments.

**Key commands:**
```bash
export EC_API_KEY="your-api-key-here"
terraform init
terraform plan
terraform apply
terraform output -raw elasticsearch_password
```

**Important gotchas:**
- Deployment template IDs and instance config IDs become `legacy` over time and cause apply failures. Use the discovery API before writing config — see the README Appendix for the `discover.sh` script.
- The `elasticsearch` block uses attribute syntax (`= {}`) not block syntax from provider `v0.6.0+`.
- When autoscaling is enabled, all autoscaleable tiers must be explicitly declared to avoid persistent plan diffs.
- Default region in examples is `azure-australiaeast`.

### `semantic-search-apm/`
Flask web app demonstrating Elasticsearch semantic search with Elastic APM instrumentation.

**Setup:**
```bash
pip install -r requirements.txt
# Set env vars: ELASTIC_APM_SERVICE_NAME, ELASTIC_APM_SECRET_TOKEN, ELASTIC_APM_SERVER_URL
python app.py
```

Uses `elastic-apm` Flask middleware for APM, `elasticsearch` Python client v8, and custom `Search` class in `search.py` for query logic.

### `search-ai-chrome-extension/`
RAG chatbot Chrome extension + Flask backend using Elasticsearch ELSER v2 for semantic search and OpenAI for response generation.

**Setup:**
```bash
pip install -r requirements.txt
# Create .env with: ELASTIC_CLOUD_ID, ELASTIC_API_KEY, OPENAI_API_KEY, SEARCH_INDEX, OPENAI_MODEL
python server.py   # starts on http://localhost:5000
```

Elasticsearch index requires `name` and `semantic_body.inference.chunks` fields. See `fields.md` for full field mapping spec. Load the Chrome extension from `chrome://extensions/` in Developer Mode.

### `prometheus-app/`
Python app that generates synthetic e-commerce traffic and exposes Prometheus metrics on port 8000.

**Run locally:**
```bash
pip install -r requirements.txt
python ecommerce_traffic_generator.py
```

**Deploy to Kubernetes:**
```bash
kubectl apply -f kubernetes/Deployment.yaml
```
The Deployment manifest deploys to the `sample-apps` namespace with `prometheus.io/scrape: "true"` annotations.

### `kafka-o117-demo/`
Kafka ICCP simulator for a Transpower/energy demo, deployed to OpenShift.

**Build and push Docker image:**
```bash
./build-and-push.sh   # pushes to docker.io/banjodocker/iccp-simulator
```

**Deploy to OpenShift:**
```bash
# Override defaults via env vars
DOCKER_IMAGE=yourusername/iccp-simulator:latest \
NAMESPACE=transpower-demo \
KAFKA_BOOTSTRAP=your-kafka-bootstrap:9092 \
bash deploy-iccp-simulators.sh
```

### `metricbeat/`
Helm chart for deploying Metricbeat as a DaemonSet on Kubernetes. Requires both the `elastic` and `prometheus-community` Helm repos.

**Install:**
```bash
helm repo add elastic https://helm.elastic.co
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install metricbeat elastic/metricbeat
```

**Run chart tests:**
```bash
cd metricbeat && make
```

Override Elasticsearch connection via `extraEnvs`: `ELASTICSEARCH_HOSTS`, `ELASTICSEARCH_USER`, `ELASTICSEARCH_PASSWORD`.

### `elastic-agent-k8s-environment/`
Kubernetes manifests for deploying Elastic Agent. Apply with `kubectl apply -f updated-elastic-agent-manifests.yaml`.

### `openshift-eck/`
Plain-text operational notes for running ECK on OpenShift/KVM. Not executable code.
