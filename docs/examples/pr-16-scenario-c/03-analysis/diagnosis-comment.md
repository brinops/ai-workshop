### Diagnosis — `LOGICAL_CONFIGURATION_ERROR`

**Root cause:** In demo/charts/payments-api/values.yaml, the PR changed `service.targetPort` from 8080 to 9090, but the Deployment only exposes container port 8080 (`app.port`, named `http`). The Service therefore routes to a port nothing listens on and would drop traffic.

**Confidence:** 93% · **Auto-remediation:** yes
**Deterministic evidence:** `LOGICAL_CONFIGURATION_ERROR` — the model agrees.

_Decision: deterministic evidence and analysis support an automatic fix_

#### Validator findings (from CI)

| Category | Check | Location | Message |
|---|---|---|---|
| LOGICAL_CONFIGURATION_ERROR | service-target-port | `demo/charts/payments-api/templates/service.yaml` | Service/rcp-validate-payments-api port 'http' targetPort 9090 does not match any container port of Deployment/rcp-validate-payments-api (container ports: [8080], names: ['http']) — traffic would be dr |

#### Proposed fix

Restore `service.targetPort` to 8080 so the Service routes to the container port the app listens on.

1. In demo/charts/payments-api/values.yaml, set `service.targetPort` from 9090 back to 8080.
2. Re-run `validate.py demo/charts` and confirm the `consistency` stage passes.
3. If exposing a metrics port is still wanted, do it as a separate change: add a metrics `containerPort` in deployment.yaml and a second named Service port. The application must actually serve metrics there.

#### Analysis

## Diagnosis: `helm-validate` failed on `consistency` (`service-target-port`)

**What broke:** The Service now forwards to a port the pod does not listen on.

| Key | Value in PR | Expected |
|---|---|---|
| `service.targetPort` (`demo/charts/payments-api/values.yaml:20`) | `9090` | `8080` |
| `app.port` / `containerPort` (named `http`) | `8080` | unchanged |

**Why:** The PR changed `targetPort: 8080` to `9090`. The Deployment exposes only container port 8080 (`app.port`), so the validator reports "targetPort 9090 does not match any container port … traffic would be dropped". The YAML, lint, template and kubeconform stages all passed, so the YAML and schema are valid and only the semantics are wrong.

**Fix:** Set `service.targetPort` back to `8080`. This is a one-line change in `values.yaml`, and no template changes are needed.

**Note:** The PR title says it exposes a metrics port, but the diff does not do that. If a metrics port is wanted, add a separate `containerPort` and a second named Service port. Do not repurpose the `http` port.
