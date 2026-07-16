"""FleetServiceStack -- EC2 host, networking, and Cognito for the fleet service.

Provisions the EC2 instance, its Elastic IP, a Route 53 A record, a security
group, the instance's IAM role, and the Cognito user pool operators
authenticate against. Depends on `ControlPlaneStack` via the
`IotAtsEndpoint` CFN export.

The instance IAM role grants Secure Tunneling open/close, fleet listing
(SearchIndex/GetThingShadow/DescribeThing), and the teleop signaling
bridge's MQTT connect/pub/sub -- a fully specified permission shape, granted
in full here.
"""

from __future__ import annotations

from typing import Any, Optional

from aws_cdk import CfnOutput, Duration, Fn, RemovalPolicy, Stack
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_ssm as ssm
from constructs import Construct

# SSM Parameter Store paths the fleet service reads at runtime -- decouples
# this stack's "hand off config" duty from guessing the service's exact
# config-loading mechanism (env file, secrets manager, etc). krabby_fleet_service
# reads these same paths; keep the two in sync if either changes.
IOT_ATS_ENDPOINT_PARAM_NAME = "/krabby/fleet/iot-ats-endpoint"
COGNITO_USER_POOL_ID_PARAM_NAME = "/krabby/fleet/cognito-user-pool-id"
COGNITO_APP_CLIENT_ID_PARAM_NAME = "/krabby/fleet/cognito-app-client-id"


class FleetServiceStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        domain_name: str,
        hosted_zone_name: str,
        cognito_domain_prefix: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        domain_name: fully-qualified DNS name for the fleet host.
        hosted_zone_name: the Route 53 hosted zone that owns `domain_name`;
            its ID is resolved via a live AWS lookup at synth time (see
            `HostedZone.from_lookup` below), which needs real AWS credentials
            to resolve and caches its result in `cdk.context.json`.
        cognito_domain_prefix: Hosted UI domain prefix; defaults to a
            per-account-unique value if omitted (Cognito domain prefixes must
            be globally unique across all AWS accounts).
        """
        super().__init__(scope, construct_id, **kwargs)

        # Single-host deployment: the account's default VPC is enough, no
        # custom networking needed for one EC2 instance in a public subnet.
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        security_group = ec2.SecurityGroup(
            self,
            "FleetServiceSecurityGroup",
            vpc=vpc,
            description=(
                "Krabby fleet service host: inbound HTTP/HTTPS (80/443) and "
                "STUN/TURN (3478 UDP, 5349 TCP/UDP). No inbound SSH -- admin "
                "access is via SSM Session Manager (instance role below), "
                "not an open port 22."
            ),
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(80),
            "HTTP -- ACME HTTP-01 challenge and HTTP->HTTPS redirect",
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS",
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.udp(3478), "STUN/TURN",
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(5349), "TURNS (TLS)",
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.udp(5349), "TURNS (DTLS)",
        )

        # AmazonSSMManagedInstanceCore makes the box reachable via SSM Session
        # Manager / Run Command -- how both interactive admin access and the
        # automated deploy restart reach the instance, with no SSH key or
        # open port 22 anywhere in this stack.
        instance_role = iam.Role(
            self,
            "FleetServiceInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )
        instance_role.add_to_policy(
            iam.PolicyStatement(
                sid="SecureTunnelingOpenClose",
                actions=[
                    "iotsecuretunneling:OpenTunnel",
                    "iotsecuretunneling:CloseTunnel",
                    "iotsecuretunneling:DescribeTunnel",
                ],
                # Secure Tunneling doesn't support resource-level permissions
                # for these actions (OpenTunnel in particular creates a tunnel
                # that has no ARN yet at call time) -- Resource: "*" is the
                # AWS-documented shape for this policy, not an over-grant.
                resources=["*"],
            )
        )
        instance_role.add_to_policy(
            iam.PolicyStatement(
                sid="FleetListing",
                actions=["iot:SearchIndex"],
                # Fleet Indexing queries the whole index, not one thing --
                # SearchIndex doesn't support resource-level permissions.
                resources=["*"],
            )
        )
        instance_role.add_to_policy(
            iam.PolicyStatement(
                sid="FleetDeviceRead",
                actions=["iot:GetThingShadow", "iot:DescribeThing"],
                resources=[f"arn:aws:iot:{self.region}:{self.account}:thing/*"],
            )
        )
        instance_role.add_to_policy(
            iam.PolicyStatement(
                sid="TeleopSignalingConnect",
                actions=["iot:Connect"],
                # The signaling bridge's own persistent MQTT connection; its
                # client ID isn't fixed by this stack, so scope to the
                # account/region rather than one specific client ARN.
                resources=[f"arn:aws:iot:{self.region}:{self.account}:client/*"],
            )
        )
        instance_role.add_to_policy(
            iam.PolicyStatement(
                sid="TeleopSignalingPublish",
                actions=["iot:Publish"],
                resources=[f"arn:aws:iot:{self.region}:{self.account}:topic/teleop/*/signaling/*"],
            )
        )
        instance_role.add_to_policy(
            iam.PolicyStatement(
                sid="TeleopSignalingSubscribe",
                actions=["iot:Subscribe"],
                resources=[f"arn:aws:iot:{self.region}:{self.account}:topicfilter/teleop/*/signaling/*"],
            )
        )
        instance_role.add_to_policy(
            iam.PolicyStatement(
                sid="TeleopSignalingReceive",
                actions=["iot:Receive"],
                resources=[f"arn:aws:iot:{self.region}:{self.account}:topic/teleop/*/signaling/*"],
            )
        )

        instance = ec2.Instance(
            self,
            "FleetServiceInstance",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            # Non-burstable: this host also runs coturn under TURN relay,
            # which can hold sustained CPU/network load that would throttle a
            # burstable instance's credit balance mid-session. c7i.large is
            # 2 vCPU / 4 GiB, non-burstable Intel, up to 12.5 Gbps network,
            # x86_64 only.
            instance_type=ec2.InstanceType("c7i.large"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=security_group,
            role=instance_role,
            require_imdsv2=True,
            # We assign a static Elastic IP explicitly below; skip the
            # subnet's auto-assigned ephemeral public IP so the instance
            # doesn't end up with two public addresses.
            associate_public_ip_address=False,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        30, volume_type=ec2.EbsDeviceVolumeType.GP3, encrypted=True,
                    ),
                )
            ],
        )

        # Static IP so the Route 53 record survives instance replacement
        # (redeploys, AZ failure recovery) without a DNS update.
        eip = ec2.CfnEIP(self, "FleetServiceEip", domain="vpc")
        ec2.CfnEIPAssociation(
            self, "FleetServiceEipAssociation",
            # `allocation_id`, not the deprecated `eip` (ref) prop --
            # AllocationId is the VPC-EIP association mechanism; `eip` is a
            # holdover from EC2-Classic.
            allocation_id=eip.attr_allocation_id, instance_id=instance.instance_id,
        )

        hosted_zone = route53.HostedZone.from_lookup(
            self, "FleetHostedZone", domain_name=hosted_zone_name,
        )
        route53.ARecord(
            self, "FleetServiceDnsRecord",
            zone=hosted_zone,
            record_name=domain_name,
            target=route53.RecordTarget.from_ip_addresses(eip.attr_public_ip),
            ttl=Duration.minutes(5),
        )

        # Cross-stack import from ControlPlaneStack. Handed to the not-yet-built
        # fleet service via an SSM Parameter rather than assumed env-file
        # plumbing, so this stack doesn't need to guess how that service will
        # eventually load its config.
        iot_ats_endpoint = Fn.import_value("IotAtsEndpoint")
        iot_ats_endpoint_param = ssm.StringParameter(
            self, "IotAtsEndpointParam",
            parameter_name=IOT_ATS_ENDPOINT_PARAM_NAME,
            string_value=iot_ats_endpoint,
            description="AWS IoT Core ATS endpoint (from ControlPlaneStack), read by krabby-fleet-service at runtime",
        )
        iot_ats_endpoint_param.grant_read(instance_role)

        # Operators authenticate here; the fleet service verifies the
        # resulting JWT rather than this stack minting per-user AWS
        # credentials. RemovalPolicy.RETAIN: destroying the stack shouldn't
        # silently delete every operator's account and lock the fleet out.
        user_pool = cognito.UserPool(
            self, "FleetOperatorPool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Membership is granted by an admin after account creation, not by
        # this stack -- being in this group is what the fleet service checks
        # before opening a tunnel on a user's behalf.
        cognito.CfnUserPoolGroup(
            self, "OperatorGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="operator",
            description="Fleet operators allowed to open SSH tunnels and view telemetry",
        )

        # Cognito Hosted UI domain prefixes are unique across all of AWS, not
        # just this account -- default to an account-scoped value so this
        # doesn't collide with another AWS customer's stack.
        domain_prefix = cognito_domain_prefix or f"krabby-fleet-{self.account}"
        user_pool_domain = user_pool.add_domain(
            "FleetPoolDomain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix=domain_prefix),
        )

        # Supports USER_SRP_AUTH (no browser) and OAuth authorization-code +
        # PKCE, no client secret needed since PKCE is the confidentiality
        # mechanism for a public client. The callback path follows the
        # NextAuth.js Cognito provider convention.
        user_pool_client = user_pool.add_client(
            "FleetOperatorClient",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL],
                callback_urls=[f"https://{domain_name}/api/auth/callback/cognito"],
                logout_urls=[f"https://{domain_name}"],
            ),
        )

        # Published to SSM Parameter Store so the JWT verification middleware
        # can read them at runtime and validate tokens against the right
        # user pool/client, without this stack guessing its config format.
        cognito_user_pool_id_param = ssm.StringParameter(
            self, "CognitoUserPoolIdParam",
            parameter_name=COGNITO_USER_POOL_ID_PARAM_NAME,
            string_value=user_pool.user_pool_id,
            description="Cognito user pool ID, read by krabby-fleet-service at runtime",
        )
        cognito_user_pool_id_param.grant_read(instance_role)
        cognito_app_client_id_param = ssm.StringParameter(
            self, "CognitoAppClientIdParam",
            parameter_name=COGNITO_APP_CLIENT_ID_PARAM_NAME,
            string_value=user_pool_client.user_pool_client_id,
            description="Cognito app client ID, read by krabby-fleet-service at runtime",
        )
        cognito_app_client_id_param.grant_read(instance_role)

        CfnOutput(self, "FleetServiceInstanceId", value=instance.instance_id)
        CfnOutput(self, "FleetServicePublicIp", value=eip.attr_public_ip)
        CfnOutput(self, "FleetServiceDomainName", value=domain_name)
        CfnOutput(
            self, "FleetCognitoUserPoolId",
            value=user_pool.user_pool_id, export_name="FleetCognitoUserPoolId",
        )
        CfnOutput(
            self, "FleetCognitoUserPoolClientId",
            value=user_pool_client.user_pool_client_id, export_name="FleetCognitoUserPoolClientId",
        )
        CfnOutput(self, "FleetCognitoDomain", value=user_pool_domain.domain_name)
