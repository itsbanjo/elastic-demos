#!/bin/bash

# Configuration variables - easily customizable
DOCKER_IMAGE="${DOCKER_IMAGE:-yourdockerhubusername/iccp-simulator:latest}"
NAMESPACE="${NAMESPACE:-transpower-demo}"
KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-transpower-kafka-kafka-bootstrap:9092}"
DEFAULT_REPLICAS="${DEFAULT_REPLICAS:-1}"
MEMORY_REQUEST="${MEMORY_REQUEST:-128Mi}"
MEMORY_LIMIT="${MEMORY_LIMIT:-256Mi}"
CPU_REQUEST="${CPU_REQUEST:-100m}"
CPU_LIMIT="${CPU_LIMIT:-200m}"

echo "=== Deploying ICCP Simulators for Transpower Demo ==="
echo "Docker Image: $DOCKER_IMAGE"
echo "Namespace: $NAMESPACE"
echo "Kafka Bootstrap: $KAFKA_BOOTSTRAP"
echo ""

# Ensure namespace exists
oc create namespace $NAMESPACE 2>/dev/null || echo "Namespace $NAMESPACE already exists"
oc project $NAMESPACE

# Apply ConfigMap first
echo "Deploying sites configuration..."
oc apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: iccp-sites-config
  namespace: $NAMESPACE
data:
  sites.json: |
    {
      "auckland-penrose": {
        "site_id": "AKL_PENROSE",
        "display_name": "Auckland Penrose 330kV",
        "lat": -36.8485,
        "lon": 174.7633,
        "customers": ["CONTACT_ENERGY", "MERCURY_ENERGY", "GENESIS_ENERGY"],
        "message_frequency": 1.5
      },
      "wellington-central": {
        "site_id": "WLG_CENTRAL", 
        "display_name": "Wellington Central 220kV",
        "lat": -41.2865,
        "lon": 174.7762,
        "customers": ["MERCURY_ENERGY", "GENESIS_ENERGY"],
        "message_frequency": 2.0
      },
      "christchurch-addington": {
        "site_id": "CHC_ADDINGTON",
        "display_name": "Christchurch Addington 66kV", 
        "lat": -43.5321,
        "lon": 172.6362,
        "customers": ["MERIDIAN_ENERGY", "CONTACT_ENERGY"],
        "message_frequency": 1.8
      },
      "huntly-power": {
        "site_id": "HUNTLY_POWER",
        "display_name": "Huntly Power Station",
        "lat": -37.5483,
        "lon": 175.0681,
        "customers": ["GENESIS_ENERGY"],
        "message_frequency": 0.8
      },
      "manapouri-power": {
        "site_id": "MANAPOURI_POWER",
        "display_name": "Manapouri Power Station",
        "lat": -45.5361,
        "lon": 167.1761,
        "customers": ["MERIDIAN_ENERGY"],
        "message_frequency": 1.0
      },
      "taupo-geothermal": {
        "site_id": "TAU_GEOTHERMAL",
        "display_name": "Taupo Geothermal Station",
        "lat": -38.7222,
        "lon": 176.0702,
        "customers": ["CONTACT_ENERGY"],
        "message_frequency": 1.2
      },
      "new-plymouth-power": {
        "site_id": "NPL_POWER",
        "display_name": "New Plymouth Power Station",
        "lat": -39.0556,
        "lon": 174.0752,
        "customers": ["GENESIS_ENERGY", "CONTACT_ENERGY"],
        "message_frequency": 1.4
      }
    }
EOF

# Define sites array - easily extensible
sites=("auckland-penrose" "wellington-central" "christchurch-addington" "huntly-power" "manapouri-power")

# Optional: Add more sites by uncommenting
# sites+=("taupo-geothermal" "new-plymouth-power")

# Function to deploy a single site
deploy_site() {
    local site=$1
    local replicas=${2:-$DEFAULT_REPLICAS}
    
    echo "Deploying ICCP simulator for: $site (${replicas} replicas)"
    
    oc apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: iccp-simulator-${site}
  namespace: $NAMESPACE
  labels:
    app: iccp-simulator
    site: ${site}
    component: transpower-iccp
spec:
  replicas: ${replicas}
  selector:
    matchLabels:
      app: iccp-simulator
      site: ${site}
  template:
    metadata:
      labels:
        app: iccp-simulator
        site: ${site}
        component: transpower-iccp
    spec:
      containers:
      - name: iccp-simulator
        image: $DOCKER_IMAGE
        env:
        - name: KAFKA_BROKERS
          value: "$KAFKA_BOOTSTRAP"
        - name: SITE_NAME
          value: "${site}"
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        - name: NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        volumeMounts:
        - name: sites-config
          mountPath: /app/config
          readOnly: true
        resources:
          requests:
            memory: "$MEMORY_REQUEST"
            cpu: "$CPU_REQUEST"
          limits:
            memory: "$MEMORY_LIMIT"
            cpu: "$CPU_LIMIT"
        readinessProbe:
          exec:
            command: ["python", "health_check.py"]
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 5
        livenessProbe:
          exec:
            command: ["python", "health_check.py"]
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
      volumes:
      - name: sites-config
        configMap:
          name: iccp-sites-config
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: node-role.kubernetes.io/worker
                operator: Exists
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: iccp-simulator
              topologyKey: kubernetes.io/hostname
EOF
    
    if [ $? -eq 0 ]; then
        echo "Successfully deployed $site"
    else
        echo "Failed to deploy $site"
        return 1
    fi
}

# Deploy all sites
for site in "${sites[@]}"; do
    # You can specify different replicas per site like this:
    case $site in
        "auckland-penrose")
            deploy_site "$site" 2  # High-traffic site gets 2 replicas
            ;;
        "huntly-power"|"manapouri-power")
            deploy_site "$site" 1  # Power stations get 1 replica
            ;;
        *)
            deploy_site "$site" $DEFAULT_REPLICAS
            ;;
    esac
    
    # Small delay between deployments to avoid overwhelming the cluster
    sleep 2
done

# Create service for simulators (optional - for monitoring/debugging)
echo ""
echo "Creating service for ICCP simulators..."
oc apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: iccp-simulators
  namespace: $NAMESPACE
  labels:
    app: iccp-simulator
    component: transpower-iccp
spec:
  selector:
    app: iccp-simulator
  ports:
  - name: health
    port: 8080
    targetPort: 8080
  clusterIP: None
EOF

# Wait for deployments to be ready
echo ""
echo "Waiting for ICCP simulators to be ready..."
for site in "${sites[@]}"; do
    echo "Waiting for iccp-simulator-${site}..."
    oc rollout status deployment/iccp-simulator-${site} -n $NAMESPACE --timeout=120s
done

echo ""
echo "=== ICCP Simulators Deployment Summary ==="
echo "ConfigMap: iccp-sites-config"
echo "Service: iccp-simulators" 
echo "Sites deployed: ${sites[*]}"
echo ""
echo "Check status with:"
echo "   oc get pods -n $NAMESPACE -l app=iccp-simulator"
echo ""
echo "View logs:"
echo "   oc logs -f deployment/iccp-simulator-auckland-penrose -n $NAMESPACE"
echo ""
echo "Monitor all simulators:"
echo "   oc get pods -n $NAMESPACE -l app=iccp-simulator -w"
echo ""
echo "Scale a specific site:"
echo "   oc scale deployment/iccp-simulator-auckland-penrose --replicas=3 -n $NAMESPACE"

# Final status check
echo ""
echo "Current deployment status:"
oc get pods -n $NAMESPACE -l app=iccp-simulator -o wide