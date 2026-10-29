### Remediation attempt 1 — ready

Restored service.targetPort from 9090 to 8080 in the payments-api chart values so the Service routes to the container port.

**Rationale:** The Deployment exposes only container port 8080 (app.port, named http), and the values comment says targetPort must match the application's port. 9090 had nothing listening, so traffic would be dropped. The service template is correct and was left unchanged.

- `demo/charts/payments-api/values.yaml` — service.targetPort 9090 → 8080

**Agent-reported validation:** validate.py reported VALID: yaml-parse, helm-lint, helm-template, kubeconform and consistency all passed.

**Scope check:** passed (2 changed lines)
**Local validation (control plane):** passed
**Commit:** `6c28a12657bd` (not pushed yet)

```diff
diff --git a/demo/charts/payments-api/values.yaml b/demo/charts/payments-api/values.yaml
index c115ed6..4dc3ba6 100644
--- a/demo/charts/payments-api/values.yaml
+++ b/demo/charts/payments-api/values.yaml
@@ -17,7 +17,7 @@ service:
   type: ClusterIP
   port: 80
   # Must route to the container port the application listens on.
-  targetPort: 9090
+  targetPort: 8080
 
 resources:
   requests:
```
