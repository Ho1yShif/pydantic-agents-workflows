# Autoscaling on Render
Source: https://render.com/docs/scaling

## Overview
Render supports manual scaling and automatic horizontal autoscaling for web services.
Autoscaling is available on paid plans (Starter instance type and above).

## Manual Scaling
Set the number of instances for a web service from 1 to N via the Dashboard or render.yaml.
Manual scaling does not require any additional configuration beyond setting the instance count.

## Autoscaling (Horizontal Scaling)
Render's autoscaler automatically adjusts the number of running instances for a web service
based on CPU and memory utilization metrics.

### How Autoscaling Works
- **minInstances**: The floor — Render always keeps at least this many instances running.
- **maxInstances**: The ceiling — Render will never scale beyond this count.
- **Scale-up trigger**: When CPU or memory exceeds the configured threshold, Render adds instances.
- **Scale-down trigger**: When utilization drops below the threshold for a sustained period,
  Render removes instances (but never below the minimum).
- **Cooldown periods**: After a scale event, autoscaling waits before triggering again to
  prevent flapping.

### Configuring Autoscaling in render.yaml
```yaml
services:
  - type: web
    name: my-app
    scaling:
      minInstances: 1
      maxInstances: 5
      targetMemoryPercent: 60   # optional, scale when memory exceeds 60%
      targetCPUPercent: 60      # optional, scale when CPU exceeds 60%
```

### Configuring Autoscaling via Dashboard
Go to your service → Settings → Scaling section. Set minimum instances, maximum instances,
and optional CPU/memory thresholds.

### Plan Requirements
Autoscaling requires a paid instance type (Starter or above). Free instances do not
support autoscaling. You must upgrade to at least the Starter plan to enable autoscaling.

### Supported Service Types
Autoscaling is available for web services. Background workers and private services
support manual instance count scaling.

### Zero Downtime During Scaling
Scale-up events add new instances before traffic is shifted to them. Existing instances
are drained gracefully on scale-down, ensuring zero-downtime during scaling events.

### Observability
Render's metrics dashboard shows instance count over time alongside CPU and memory metrics,
so you can verify autoscaling behavior and tune your thresholds.

## Instance Types for Scaling
- **Free**: No autoscaling support, single instance only
- **Starter**: Autoscaling supported, good for low-traffic apps
- **Standard**: Autoscaling supported, suitable for production workloads
- **Pro**: Autoscaling supported, high-performance workloads
- **Pro Max, Pro Ultra**: Autoscaling supported, maximum performance

## render.yaml Scaling Examples
Single fixed instance (no autoscaling):
```yaml
numInstances: 1
```

Autoscaling between 2 and 10 instances based on CPU:
```yaml
scaling:
  minInstances: 2
  maxInstances: 10
  targetCPUPercent: 70
```
