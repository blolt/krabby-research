# `FleetServiceStack`

The EC2 host, networking, and Cognito user pool the fleet service and portal
will run on. Application code and systemd units are a separate deliverable —
this stack is infrastructure only. Defined in `fleet_service_stack.py`.
Depends on `ControlPlaneStack` (imports its `IotAtsEndpoint` export).

## Required context values

No domain has been registered yet, so these aren't hardcoded constants —
they're required CDK context, passed as `-c key=value` on the command line
rather than environment variables.

| Context key | Placeholder | Purpose |
|---|---|---|
| `domainName` | `{domain-name}` | Fully-qualified DNS name for the fleet host |
| `hostedZoneName` | `{hosted-zone-name}` | The Route 53 hosted zone that owns the domain above -- its ID is resolved via a live AWS lookup at synth time, not supplied directly |
| `cognitoDomainPrefix` (optional) | `{cognito-domain-prefix}` | Cognito Hosted UI domain prefix — must be globally unique across AWS; defaults to `krabby-fleet-<account-id>` if unset |

## Deploy

```
cd fleet/infra
source .venv/bin/activate
./scripts/deploy-fleet-service.sh \
  -c domainName={domain-name} \
  -c hostedZoneName={hosted-zone-name}
```

Requires `ControlPlaneStack` to already be deployed (its `IotAtsEndpoint`
export must exist). See [README.md](README.md) for the shared deploy-script
behavior (credential checks, identity confirmation prompt).

This stack looks up the account's default VPC (`ec2.Vpc.from_lookup`) and the
hosted zone's ID (`route53.HostedZone.from_lookup`), both of which need real
AWS credentials to resolve — the first `cdk synth`/`diff`/`deploy` against a
real account writes the results to `fleet/infra/cdk.context.json`. Commit
that file once it has real values, so later synths (and CI) resolve to the
same VPC/subnet/AZ/hosted-zone data instead of re-querying AWS every time.

## Resources

| Resource | Type | Purpose |
|---|---|---|
| `FleetServiceSecurityGroup` | `AWS::EC2::SecurityGroup` | Inbound 80/443 (Caddy: ACME challenge + app traffic), 3478 UDP + 5349 TCP/UDP (coturn). No inbound SSH. |
| `FleetServiceInstanceRole` | `AWS::IAM::Role` | EC2 instance role: `AmazonSSMManagedInstanceCore` (Session Manager / Run Command, no SSH key needed) + Secure Tunneling `OpenTunnel`/`CloseTunnel`/`DescribeTunnel` + fleet listing (`iot:SearchIndex`/`GetThingShadow`/`DescribeThing`) + teleop signaling bridge (`iot:Connect`/`Publish`/`Subscribe`/`Receive` on `teleop/*/signaling/*`). Granted up front even though the code that uses SearchIndex and the signaling bridge doesn't exist yet — the permission shape is already fully specified. |
| `FleetServiceInstance` | `AWS::EC2::Instance` | `c7i.large` (see rationale in `fleet_service_stack.py`), Amazon Linux 2023, IMDSv2 required, 30 GiB encrypted gp3 root volume, no auto-assigned public IP (uses the EIP below instead). |
| `FleetServiceEip` / `FleetServiceEipAssociation` | `AWS::EC2::EIP` / `AWS::EC2::EIPAssociation` | Static public IP so the DNS record survives instance replacement. |
| `FleetServiceDnsRecord` | `AWS::Route53::RecordSet` | A record for `domainName` in the given hosted zone, pointed at the EIP. |
| `IotAtsEndpointParam` | `AWS::SSM::Parameter` (`/krabby/fleet/iot-ats-endpoint`) | `ControlPlaneStack`'s `IotAtsEndpoint` export, handed off via SSM Parameter Store for the fleet service to read at runtime. Instance role has read access. |
| `FleetOperatorPool` | `AWS::Cognito::UserPool` | Operator accounts. No self-sign-up (admin-created only). `RemovalPolicy.RETAIN`. |
| `OperatorGroup` | `AWS::Cognito::UserPoolGroup` (`operator`) | Membership grants tunnel/telemetry access; assigned manually by an admin, not by this stack. |
| `FleetPoolDomain` | Cognito Hosted UI domain | `cognitoDomainPrefix` (or the account-scoped default). |
| `FleetOperatorClient` | `AWS::Cognito::UserPoolClient` | One client for both the CLI (`USER_SRP_AUTH`) and the portal (OAuth authorization-code + PKCE, no client secret). |
| `FleetServiceInstanceId`, `FleetServicePublicIp`, `FleetServiceDomainName`, `FleetCognitoUserPoolId`, `FleetCognitoUserPoolClientId`, `FleetCognitoDomain` (outputs) | `CfnOutput` | For the fleet service/portal/CLI config and for console visibility. `FleetCognitoUserPoolId` and `FleetCognitoUserPoolClientId` are also exported for cross-stack use. |

## Remove the stack

```
cd fleet/infra
source .venv/bin/activate
./scripts/destroy-fleet-service.sh \
  -c domainName={domain-name} \
  -c hostedZoneName={hosted-zone-name}
```

(CDK has to construct the stack to destroy it, so the same context values
used to deploy are required here too.)

### Manual steps that may block destroy or need cleanup after

- **`FleetOperatorPool` isn't deleted.** `RemovalPolicy.RETAIN` means destroy
  doesn't fail here, but the user pool (and every operator account) is left
  behind, orphaned from the stack. Delete manually via the Cognito console or
  `aws cognito-idp delete-user-pool` if you want a full cleanup.
- **`ControlPlaneStack` destroy ordering.** This stack imports
  `ControlPlaneStack`'s `IotAtsEndpoint` export, so `ControlPlaneStack` can't
  be destroyed while this stack still exists — destroy `FleetServiceStack`
  first (the explicit `add_dependency` in `app.py` also makes
  `cdk deploy ControlPlaneStack FleetServiceStack` order correctly on
  deploy).

If `cdk destroy` fails partway through, resolve the blocker and re-run —
CloudFormation resumes the rollback from where it stopped.
