"""One native cached-image transfer; its contract is separate from launch identity."""

import importlib
import json
import subprocess

previous = importlib.import_module("run-native772-advance-r49-real-wheel-acceptance")
native = previous.native
R, C, D = previous.R, previous.C, previous.D
B = D / "ssd17-official-image-migration-source-r1"
SOURCE_SHA = "920b17f2161152a4a172e1ffa67d7a23740ae1c945855e883f0f9c03cdaad7ac"
DEPLOYMENT_SHA = "2da1abefed7fd9dd7ba72c2d0e903f869736a696d276cce9ee344aa3c1340a66"
BINDING_SHA = "1b7b4349e776cad3a21e5e3572afac863da679d649cc871cbd427cb53259aedc"


def copy_contract(binding, raw):
    payload = dict(path=binding["admission_path_on17"], text=raw)
    script = (
        "payload="
        + repr(payload)
        + "\n"
        + """
from pathlib import Path
import hashlib,json,os
p=Path(payload['path']);data=payload['text'].encode()
if p.exists():
    if p.read_bytes()!=data:raise RuntimeError('Existing asset contract conflicts; no overwrite')
else:
    with p.open('xb')as f:f.write(data);f.flush();os.fsync(f.fileno())
print(json.dumps(dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest())))
"""
    )
    result = subprocess.run(
        binding["ssh_argv"] + ["python3", "-"],
        input=script,
        text=True,
        capture_output=True,
        timeout=18,
    )
    if result.returncode:
        raise RuntimeError("Native17 contract staging failed: " + result.stderr[-1500:])
    return json.loads(result.stdout)["sha256"]


def advance(owner, state, launch):
    if native.read(C / "NATIVE_ADVANCE_OWNER.json") != owner:
        raise RuntimeError("Only the sole controller may admit an asset transfer")
    source = B / "migrate_frozen_official_image_to_ssd17_r1.py"
    deployment = B / "SSD17_BACKEND_DEPLOYMENT_R1.json"
    binding_path = D / "ssd17-network-r1/ROOT_NODE17_SSH_BINDING_ACTUAL_R1.json"
    if (
        native.sha(source) != SOURCE_SHA
        or native.sha(deployment) != DEPLOYMENT_SHA
        or native.sha(binding_path) != BINDING_SHA
    ):
        raise RuntimeError("Frozen native image preparation source or backend differs")
    binding = native.read(binding_path)
    registry = B / "ROOT_IMAGE_LAUNCH_REGISTRY_R1.json"
    contract = B / "ROOT_IMAGE_MIGRATION_CONTRACT_ACTUAL_R1.json"
    if not registry.exists():
        value = dict(
            template_only=False,
            source_sha256=SOURCE_SHA,
            deployment_sha256=DEPLOYMENT_SHA,
            unique_controller_owner=owner,
            task_ids=["fix-git"],
            max_concurrent_image_transfers=1,
            required_evidence=dict(
                node17_ssh_binding=dict(path=str(binding_path), sha256=BINDING_SHA)
            ),
        )
        if contract.exists():
            if native.read(contract) != value:
                raise RuntimeError(
                    "Preserve the existing image contract; no reinitialization"
                )
        else:
            native.write(contract, value)
        if copy_contract(binding, contract.read_text()) != native.sha(contract):
            raise RuntimeError("The native17 contract is not the same frozen bytes")
    elif not contract.exists():
        raise RuntimeError("Existing launch without its contract requires an audit")
    state["ssd17_image_preparation"] = launch(
        "qwen35-reliability-ssd17-fixgit-image-migration-20261103-r1.service",
        str(source),
        [
            "--deployment",
            str(deployment),
            "--admission",
            str(contract),
            "--task-id",
            "fix-git",
            "--role",
            "controller",
            "--output-dir",
            str(B / "actual-run-r1"),
        ],
        registry,
        owner,
        dict(
            deployment_sha256=DEPLOYMENT_SHA,
            contract_sha256=native.sha(contract),
            model_generation_calls=0,
            image_transfer_concurrency=1,
            original_task_or_Verifier_modified=False,
            source149_archive_written=False,
        ),
        native_python=R / "env/harbor-reliability-r1/bin/python",
    )
