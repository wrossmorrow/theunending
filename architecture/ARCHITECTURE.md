# The Unending: system architecture

How a prompt typed into the admin page becomes a published set on theunending.ai.
Two views of the same system: **who calls whom**, then **where the bytes go**.

## 1. Control: requests, jobs, callbacks

```mermaid
%%{init: {"theme": "neutral", "flowchart": {"curve": "basis", "nodeSpacing": 40, "rankSpacing": 60}}}%%
flowchart LR
  you(["You<br/>admin page"])

  subgraph aws ["AWS · private VPC behind an NLB"]
    nlb["NLB<br/>TLS · admin.theunending.ai"]
    envoy["Envoy<br/>ext_proc Bearer auth"]
    api["Admin API<br/>FastAPI"]
    pg[("Postgres<br/>sets · drafts · runs · outbox")]
    relay["Outbox relay"]
    publish["Fargate task<br/>publish"]
    sns["SNS"]
  end

  subgraph modal ["Modal"]
    dispatch["Dispatcher<br/>CPU web endpoint"]
    evaluate["evaluate<br/>GPU · 3×3 draft grid"]
    batch["batch<br/>GPU · 5000 images + embeddings"]
  end

  email(["Email"])

  you -- "HTTPS + Bearer" --> nlb --> envoy --> api
  api <--> pg
  pg -- "outbox rows" --> relay
  relay -- "draft · batch" --> dispatch
  dispatch --> evaluate
  dispatch --> batch
  relay -- "ecs:RunTask" --> publish

  evaluate -. "status" .-> nlb
  batch -. "status" .-> nlb
  publish -. "status" .-> nlb

  api -- "terminal states" --> sns --> email

  classDef gpu stroke:#900000,stroke-width:2px,color:#900000;
  classDef person fill:#1a1a1a,stroke:#1a1a1a,color:#fff;
  class evaluate,batch gpu;
  class you,email person;
```

## 2. Data: generation, publishing, going live

```mermaid
%%{init: {"theme": "neutral", "flowchart": {"curve": "basis", "nodeSpacing": 40, "rankSpacing": 60}}}%%
flowchart LR
  you(["You<br/>admin page"])
  visitor(["Visitors"])

  hf[("Modal volume<br/>HF model cache")]
  evaluate["evaluate · batch<br/>Modal GPU"]
  runs[("S3 runs bucket<br/>drafts/ · runs/")]
  api["Admin API"]
  publish["Fargate publish<br/>posters · thumbs · OG · similars"]
  site[("S3 site bucket<br/>assets/ write-once")]
  repo["GitHub repo<br/>draft PR"]
  cf["CloudFront<br/>theunending.ai"]

  hf --> evaluate
  evaluate -- "PUT via OIDC role" --> runs
  api -- "presigned URL" --> you
  runs -. "grid preview" .-> you

  runs -- "read" --> publish
  publish -- "PUT If-None-Match" --> site
  publish -- "per-set data · draft post<br/>(GitHub App)" --> repo
  repo -- "merge → just sync" --> site
  site --> cf --> visitor

  classDef gpu stroke:#900000,stroke-width:2px,color:#900000;
  classDef person fill:#1a1a1a,stroke:#1a1a1a,color:#fff;
  class evaluate gpu;
  class you,visitor person;
```

## Notes

- **One way in.** People and jobs both reach the API through the NLB (TLS) and Envoy (Bearer check in
  ext_proc), so every status change passes the same auth. The EC2 box running Envoy, the API and
  Postgres sits in a private subnet; only the NLB is public.
- **The outbox is the only path to the outside world.** A commit or publish writes its outbox row in
  the same transaction as the state change; the relay launches the Modal job or Fargate task
  afterwards, so a duplicate request can't start a second batch.
- **No long-lived cloud keys in jobs.** Modal assumes an AWS role through OIDC; the Fargate task uses
  its task role; the admin box uses its instance profile. Private subnets reach S3 through a gateway
  endpoint and ECR through interface endpoints.
- **Published assets are write-once.** The publish role can only `PutObject` with `If-None-Match: *`
  under `assets/`, and has no delete permission anywhere.
- **Every publish only adds files.** The PR adds `_data/set_streams/<post>.json`,
  `_data/set_posters/<post>.json`, the stream manifest, the OG tile and a `_drafts/` post;
  `_plugins/set_data.rb` merges the per-set files at build time.
- **Backups.** A timer runs `pg_dump -Fc` and streams it to S3.
- **Planned:** a reconciler for runs that never report back (Modal call / ECS task status vs. S3
  contents), and a run-events log behind the status endpoint.
