# `ControlPlaneStack`

Shared IoT resources every enrolled robot uses: thing type, per-thing
device policy, Fleet Indexing, lifecycle events, and the S3/IAM/RoleAlias
path for agent-reported camera frames. Defined in `control_plane_stack.py`.

## Deploy

```
cd fleet/infra
source .venv/bin/activate
./scripts/deploy-control-plane.sh
```

See [README.md](README.md) for the shared deploy-script behavior
(credential checks, identity confirmation prompt).

## Resources

| Resource | Type | Purpose |
|---|---|---|
| `KrabThingType` | `AWS::IoT::ThingType` | Groups every enrolled robot so `SearchIndex` can filter on "all krabs" as a class. |
| `KrabDevicePolicy` | `AWS::IoT::Policy` | Per-thing IoT policy (shadow, `teleop/*/signaling/*`, `tunnels/notify`), scoped via `${iot:Connection.Thing.ThingName}`. Attached to every device cert by `krabby enroll`. |
| `FleetIndexing` | Custom resource (`updateIndexingConfiguration`) | Enables Fleet Indexing: registry + Classic Shadow + connectivity status. No native CFN resource exists for this. |
| `EnableIotLifecycleEvents` | Custom resource (`updateEventConfigurations`) | Turns on THING/CERTIFICATE lifecycle events, which feed Fleet Indexing's `connectivity.connected`/`timestamp` fields. |
| `DescribeIotAtsEndpoint` | Custom resource (`describeEndpoint`, read-only) | Looks up the account's ATS MQTT data endpoint. |
| `DescribeIotCredentialProviderEndpoint` | Custom resource (`describeEndpoint`, read-only) | Looks up the account's IoT Credentials Provider endpoint (for image-upload cert-to-AWS-credential exchange). |
| `KrabReportedImages` | `AWS::S3::Bucket` | Destination for agent-reported camera frames (`reported_image` is an S3 reference, not inline shadow bytes). 30-day expiration lifecycle rule; `RemovalPolicy.RETAIN`. |
| `KrabImageUploadRole` | `AWS::IAM::Role` | Trusted by `credentials.iot.amazonaws.com`; grants `s3:PutObject` on `KrabReportedImages`. |
| `KrabImageRoleAlias` | `AWS::IoT::RoleAlias` | Lets a device swap its cert for temporary credentials scoped to `KrabImageUploadRole`, via `AssumeRoleWithCertificate`. |
| `IotAtsEndpoint`, `IotCredentialProviderEndpoint`, `KrabReportedImagesBucketName` (outputs) | `CfnOutput`, exported | For `krabby enroll`/`agent` and `FleetServiceStack` to import. |
| `KrabThingTypeName`, `KrabDevicePolicyName`, `KrabImageRoleAliasName` (outputs) | `CfnOutput`, not exported | Console visibility only -- the actual values are fixed constants enroll/agent import directly in code. |

## Bench E2E

Live pytest suite in [`tests_e2e/`](tests_e2e/README.md). Set `BENCH_E2E=1`
and run against the enrolled bench thing; skipped by default so local synth /
unit workflows stay offline.

## Remove the stack

```
cd fleet/infra
source .venv/bin/activate
./scripts/destroy-control-plane.sh
```

### Manual steps that may block destroy

- **`KrabDevicePolicy` still attached to a certificate.** CloudFormation
  cannot delete an IoT policy while any device certificate has it attached.
  List every attached certificate ARN with `aws iot list-targets-for-policy
  --policy-name KrabDevicePolicy` (the AWS CLI auto-paginates, so this
  returns all targets even across a fleet of hundreds/thousands of robots),
  then detach each one:

  ```
  aws iot list-targets-for-policy --policy-name KrabDevicePolicy \
    --query 'targets' --output text | tr '\t' '\n' | while read -r arn; do
    aws iot detach-policy --policy-name KrabDevicePolicy --target "$arn"
  done
  ```

  Or deactivate/delete the cert entirely if the device is being
  decommissioned rather than just unenrolled.
- **`KrabThingType` not deprecated.** AWS IoT generally requires a thing type
  to be deprecated before it can be deleted; `CfnThingType` doesn't automate
  this step. If destroy fails here, deprecate it first:
  `aws iot deprecate-thing-type --thing-type-name Krab`.
- **Fleet Indexing / lifecycle events aren't reverted.** These are
  account-wide singletons, not stack-scoped resources -- there's no previous
  state for CDK to restore to, and force-disabling them on every stack
  teardown could break Fleet Indexing for the whole account if something
  else also depends on it being on. So the three custom resources (Fleet
  Indexing config, lifecycle events, ATS endpoint lookup) intentionally have
  no `on_delete` handler; destroying the stack leaves them configured as-is.
  Disable manually if you want a full account reset:
  `aws iot update-indexing-configuration` / `aws iot update-event-configurations`.
- **`KrabReportedImages` bucket isn't deleted.** `RemovalPolicy.RETAIN`
  means destroy doesn't fail here, but the bucket and every uploaded image
  are left behind, orphaned from the stack. Delete manually if you want a
  full cleanup: empty the bucket, then `aws s3 rb s3://<bucket-name>`.

If `cdk destroy` fails partway through, resolve the blocker and re-run --
CloudFormation resumes the rollback from where it stopped.
