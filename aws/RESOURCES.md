# Existing AWS Resources — AmSC L2 Model Services (us-east-2)

Audit of the 51 resources currently in the *AmSC L2 Model Services* account
(account `890890990154`, region `us-east-2`), captured from the myApplications
*Add resources* picker on 2026-04-27.

Each row is classified as:

- **REUSE** — wire the new LightshowAI stack to this existing resource
- **REUSE+EXTEND** — keep the resource, add new entries / configuration to it
- **REPLACE** — provision a parallel resource for LightshowAI; do not touch this one
- **IGNORE** — unrelated to LightshowAI; leave alone
- **ADD-TO-APP** — bundle into the new myApplication group, no functional dependency

---

## Page 1 (resources 1–10)

| # | Identifier | Service | Type | Action | Notes |
|---|---|---|---|---|---|
| 1  | `DefaultConfiguration/1/00000…` | apprunner | autoscaling-config | **REUSE** | Default App Runner autoscaling config — fine for the 3 new services |
| 2  | `default.postgres17` | rds | pg parameter group | **REUSE** | Parameter group only; the actual DB is `postgresdb-E6Rw5n` (page 3) |
| 3  | `sgr-0b8a0583f574aa420` | ec2 | sg-rule | **REUSE** | VPC SG rule (likely MemoryDB / RDS ingress) — verify with describe |
| 4  | `sg-0da4a61b0b54fb93a` | ec2 | security-group | **REUSE** | VPC SG — see whether this is the data-plane SG to attach App Runner VPC connector to |
| 5  | `rtb-0dc9020198d1c5091` | ec2 | route-table | **REUSE** | Existing VPC route table |
| 6  | `primary` | athena | workgroup | **REUSE** | Use for ad-hoc analytics over `result_store` snapshots |
| 7  | `default.memorydb-redis6` | memorydb | parameter-group | **REUSE** | Param group for the existing Redis 6 cluster |
| 8  | `subnet-0c047235a5b26ea78` | ec2 | subnet | **REUSE** | Private subnet for App Runner VPC connector |
| 9  | `default.memorydb-valkey7.search` | memorydb | parameter-group | **REUSE** | **Valkey 7 + search module → vector RAG store** for past XAS comparisons |
| 10 | `sg-0c30abd3a37c3afd1` | ec2 | security-group | **REUSE** | Likely VPC connector SG — confirm |

## Page 2 (11–20)

| # | Identifier | Service | Type | Action | Notes |
|---|---|---|---|---|---|
| 11 | `sgr-0c6b97bf71331a…` | ec2 | sg-rule | **REUSE** | VPC SG rule |
| 12 | `datadog-Mvhq49` | secretsmanager | secret | **IGNORE** | Datadog API key — observability, unrelated to LightshowAI |
| 13 | `default` | elasticache | user | **IGNORE** | ElastiCache user (not MemoryDB) — no plans to use ElastiCache here |
| 14 | `igw-0cbc67b7d5af66…` | ec2 | internet-gateway | **REUSE** | VPC IGW |
| 15 | `amsc-prod-model-sv…` | s3 | bucket | **REUSE+EXTEND** | **Likely existing model store** — add `lightshowai/` prefix for OmniXAS checkpoints if we ever want to externalize them |
| 16 | `amsc-prod-artifactbu…` | s3 | bucket | **REUSE+EXTEND** | **Artifact bucket** — add `lightshowai/` prefix for HTML/PNG plots, MLflow artifacts |
| 17 | `kong-yeLPin` | secretsmanager | secret | **IGNORE** | Kong API gateway secret — separate platform |
| 18 | `default` | events | event-bus | **REUSE** | Default EventBridge bus — schedule nightly benchmarks |
| 19 | `open-access` | memorydb | acl | **REUSE** | MemoryDB ACL — likely lets the `default` user (page 4 #38) read/write |
| 20 | `sg-0a7e036aa2aec51f6` | ec2 | security-group | **REUSE** | VPC SG — verify role |

## Page 3 (21–30)

| # | Identifier | Service | Type | Action | Notes |
|---|---|---|---|---|---|
| 21 | `acl-064fb0f291281f…` | ec2 | network-acl | **REUSE** | VPC NACL |
| 22 | `subnet-0c0e06184ee…` | ec2 | subnet | **REUSE** | Subnet (likely public) |
| 23 | `dopt-0a2176aee1b2…` | ec2 | dhcp-options | **REUSE** | VPC DHCP options |
| 24 | `sgr-0512244d5877b…` | ec2 | sg-rule | **REUSE** | SG rule |
| 25 | `subnet-057a291797…` | ec2 | subnet (1 tag) | **REUSE** | Tagged subnet — probably private app subnet |
| 26 | `dockerhub-2c0ouj` | secretsmanager | secret | **REUSE** | Docker Hub credentials — useful if any base images come from DH |
| 27 | `postgresdb-E6Rw5n` | secretsmanager | secret | **REUSE** | **RDS Postgres master credentials** — backend for MLflow + result_store |
| 28 | `default.memorydb-v…` | memorydb | parameter-group | **REUSE** | Likely the Valkey param group (truncated name) |
| 29 | `sgr-00101edd38b94…` | ec2 | sg-rule | **REUSE** | SG rule |
| 30 | `AwsDataCatalog` | athena | datacatalog | **REUSE** | Default Athena Glue catalog |

## Page 4 (31–40)

| # | Identifier | Service | Type | Action | Notes |
|---|---|---|---|---|---|
| 31 | `subnet-09ba551969…` | ec2 | subnet | **REUSE** | Subnet |
| 32 | `f17d571b-bff0-40ec-…` | acm | certificate | **REUSE?** | ACM cert — confirm the domain (probably `*.amsc-prod` or similar). Reuse for `xas-ui` if a wildcard / matching name |
| 33 | `sgr-024b85d0f393cf…` | ec2 | sg-rule | **REUSE** | SG rule |
| 34 | `sg-0197731bd9e287…` | ec2 | security-group | **REUSE** | SG |
| 35 | `sgr-060a4b08a8770f…` | ec2 | sg-rule | **REUSE** | SG rule |
| 36 | `sgr-0059afc3811a97…` | ec2 | sg-rule | **REUSE** | SG rule |
| 37 | `subnet-0c8cb182557…` | ec2 | subnet (1 tag) | **REUSE** | Tagged subnet |
| 38 | `default` | memorydb | user | **REUSE** | MemoryDB user — used in ACL `open-access` |
| 39 | `mlflow-ynKQQb` | secretsmanager | secret | **REUSE** | **MLflow service credentials** — basic auth for the existing MLflow instance |
| 40 | `default.memorydb-r…` | memorydb | parameter-group | **REUSE** | Likely Redis param group (already counted as #7) — possibly a second cluster |

## Page 5 (41–50)

| # | Identifier | Service | Type | Action | Notes |
|---|---|---|---|---|---|
| 41 | `sgr-02d3af066519a1…` | ec2 | sg-rule | **REUSE** | SG rule |
| 42 | `default.memorydb-r…` | memorydb | parameter-group | **REUSE** | Param group |
| 43 | `e194cd09-cdb3-4e2…` | acm | certificate | **REUSE?** | Second ACM cert — verify domain (could be `mlflow.…`) |
| 44 | `mlflow-tg/a7eec50e…` | elasticloadbalancing | target-group | **REUSE** | **MLflow ALB target group → MLflow is already deployed and reachable.** Reuse the existing tracking server instead of provisioning a new one |
| 45 | `stackset-childrole/a9…` | cloudformation | stack | **IGNORE** | This account is a StackSet child — managed centrally. Do not touch |
| 46 | `cf-templates-c7q3wo…` | s3 | bucket | **IGNORE** | CloudFormation template staging bucket — leave alone |
| 47 | `sgr-017ae4e6d70ae8…` | ec2 | sg-rule | **REUSE** | SG rule |
| 48 | `key-07d760225c307…` | ec2 | key-pair | **IGNORE** | EC2 SSH key — App Runner doesn't need one |
| 49 | `vpc-04a203dea34fc5…` | ec2 | vpc | **REUSE** | **The VPC.** Anchor for everything network-related |
| 50 | `default.memorydb-r…` | memorydb | parameter-group | **REUSE** | Param group |

## Page 6 (51)

| # | Identifier | Service | Type | Action | Notes |
|---|---|---|---|---|---|
| 51 | `sgr-0ec95884692dca…` | ec2 | sg-rule | **REUSE** | SG rule |

---

## Aggregate findings

### Already in place — do NOT re-provision

| Layer | Existing resource(s) | Action |
|---|---|---|
| **VPC** | `vpc-04a203dea34fc5…` + 5 subnets + IGW + RT + NACL + DHCP opts | Use `Vpc.from_lookup()` in CDK; never `new Vpc(...)` |
| **MemoryDB Redis 6** | param group `default.memorydb-redis6` (cluster name not visible — get via API) | Use as request cache |
| **MemoryDB Valkey 7 search** | param group `default.memorydb-valkey7.search` + ACL `open-access` + user `default` | Use as vector RAG store |
| **RDS Postgres 17** | param group `default.postgres17` + secret `postgresdb-E6Rw5n` | Backend for MLflow already; reuse for `result_store` schema |
| **MLflow service** | ALB target group `mlflow-tg/a7eec50e…` + secret `mlflow-ynKQQb` + ACM cert (likely #43) | **Skip MLflow stack entirely** — point bench-runner at the existing endpoint |
| **S3 buckets** | `amsc-prod-model-sv…`, `amsc-prod-artifactbu…` | Add `lightshowai/` prefix; no new bucket needed |
| **ACM certs** | 2 certs (#32, #43) | Reuse if a matching domain is available; otherwise request a new one in CDK |
| **App Runner autoscaling** | `DefaultConfiguration/1/000…` | Attach to all 3 new App Runner services |
| **Athena** | workgroup `primary` + `AwsDataCatalog` | Use for ad-hoc result_store queries |
| **EventBridge** | `default` event bus | Use for nightly benchmark schedule |
| **Secrets** | `dockerhub-2c0ouj` | Use to authenticate ECR base-image pulls if needed |

### NOT in the account — must add

| Resource | Why |
|---|---|
| **3 ECR repos** (`xas-ui`, `omnixas-api`, `mcp-gateway`) | Container registry for the new images. **Note**: bench-runner reuses the `omnixas-api` image |
| **Cognito User Pool + App Client + Hosted UI domain** | Auth for the public `xas-ui` and Bearer auth for `mcp-gateway` |
| **3 App Runner services** (`xas-ui`, `omnixas-api`, `mcp-gateway`) | New compute |
| **App Runner VPC connector** | So new services reach MemoryDB + RDS in private subnets |
| **2 Secrets Manager entries** (`MP_API_KEY`, `ANTHROPIC_API_KEY`) | New credentials |
| **AWS Batch on Fargate** (compute env + job queue + job definition) | Periodic benchmarks |
| **EventBridge rule** | Nightly trigger for benchmark suite |
| **CloudWatch dashboard + alarms** | Per-service health, latency, cache hit rate |

### Notes / things to verify before the first deploy

1. **VPC private vs public subnet identification** — 5 subnets are visible but the picker doesn't say which are public/private. Need `aws ec2 describe-subnets` to identify the private ones for the App Runner VPC connector and the public ones for any ALB.
2. **MemoryDB cluster names + endpoints** — the picker only shows param groups / ACL / user, not the actual cluster ARNs. Need `aws memorydb describe-clusters`.
3. **MLflow endpoint URL** — `mlflow-tg/a7eec50e…` is a target group, but we need the ALB DNS or custom domain to point clients at. Need `aws elbv2 describe-load-balancers` + `describe-listeners` + look at the ACM cert SANs.
4. **CloudFormation StackSet** — this account is a child in a StackSet. Anything we deploy via CDK must coexist; in particular, do not modify resources tagged with `aws:cloudformation:stack-name`.
5. **No existing ECR repos** in pages 1–6 — confirm with `aws ecr describe-repositories`. If none exist, the CDK `ECR stack` is the first thing to deploy.
6. **Are the App Runner autoscaling config + the 3 future services the *only* App Runner footprint?** — none of the 51 resources is an `apprunner:service`, so this looks like a brand-new App Runner footprint.
