"""CDK app entry for Krabby fleet infra."""

from __future__ import annotations

import os

import aws_cdk as cdk

from control_plane_stack import ControlPlaneStack

app = cdk.App()

ControlPlaneStack(
    app,
    "ControlPlaneStack",
    description="Krabby fleet IoT control plane (thing type, device policy, Fleet Indexing, presence)",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
    ),
)

app.synth()
