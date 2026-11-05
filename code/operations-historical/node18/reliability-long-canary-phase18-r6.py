"""Eight registered native long-task diagnostics; no repaired comparison admission."""

import importlib

base = importlib.import_module("reliability-cold-serving18-r4")
R, C, D = base.R, base.C, base.D
B = D / "long-ab8-r2"
PLAN_SHA = "3654c8b6d1ca35e35a95a2836c3a365c4ceeed8d8e87bab5b76cba9164a97128"
WORKER_SHA = "ead8f31e06f1e5bc9434516f4b29dccf5559717f250c2a0b434ce0758bd8d9d8"
IPAM_SHA = "aac8897a4502f163bf2eac0cefe3aca388dd7727b5523a58c13d6cdb6e1a933c"
FIXTURE_SHA = "af1d80cec96b714296040157607a21dcf0377a9e485ba9df9995a31ab62f080c"


def advance(owner, state, launch):
    if base.read(C / "NATIVE_ADVANCE_OWNER.json") != owner:
        raise RuntimeError("Native diagnostic admission requires the unique controller")
    state["repaired_comparison_scope"] = dict(
        common30_models=6,
        common30_trials=180,
        synthetic32_trials=32,
        total_new_primary_trials=212,
        admission=False,
        historical_results_are_engineering_diagnostics_only=True,
        old_winner267_and_old801_admission=False,
    )
    if not (R / "checks/NATIVE_ADVANCE_R46_HANDOFF_COMPLETED.json").exists():
        state["long_ab8_canary"] = dict(
            status="WAITING_CONTROLLED_HANDOFF", formal_ready=False
        )
        return
    plan, source = (
        B / "DIAGNOSTIC_LONG_AB8_MANIFEST_R2.json",
        B / "run_long_ab8_native18_r2.py",
    )
    if base.sha(plan) != PLAN_SHA or base.sha(source) != WORKER_SHA:
        raise RuntimeError("Registered eight-Trial diagnostic changed")
    policy_path = D / "NEW_PROTOCOL_DOCKER_NAMESPACE_POLICY_R2.json"
    policy = base.read(policy_path)
    if not policy["frozen"] or policy["admitted_namespaces"] != [
        "q35relfix1",
        "q35relcan1",
    ]:
        raise RuntimeError(
            "Only fixture and finite eight-Trial namespaces may be admitted"
        )
    privacy = (
        R
        / "lifecycle-boundary-r1/recorder-privacy-fixtures-r3/FIXTURE_ACCEPTANCE_R3.json"
    )
    ipam = B / "ACTUAL_IPAM_PREFLIGHT_R1.json"
    if (
        base.sha(privacy) != FIXTURE_SHA
        or base.sha(ipam) != IPAM_SHA
        or not base.read(ipam)["passed"]
    ):
        raise RuntimeError(
            "Real native fixture or actual Engine IPAM evidence is missing"
        )
    admission = B / "ROOT_ADMISSION_ACTUAL_R1.json"
    output = B / "actual-run-r1"
    argv = [
        "--plan",
        str(plan),
        "--admission",
        str(admission),
        "--owner-state",
        str(C / "NATIVE_ADVANCE_OWNER.json"),
        "--output-dir",
        str(output),
        "--job-configs",
        str(B / "configs/m0.json"),
        str(B / "configs/new-m2-e5.json"),
    ]
    extra = dict(
        plan_path=str(plan),
        plan_sha256=PLAN_SHA,
        namespace="q35relcan1",
        namespace_policy_path=str(policy_path),
        namespace_policy_sha256=base.sha(policy_path),
        docker_guard_path=str(D / "native-client-bin-r1/docker"),
        fresh_ipam_nonoverlap_verified=True,
        fresh_ipam_proof_path=str(ipam),
        fresh_ipam_proof_sha256=IPAM_SHA,
        required_evidence=dict(
            native_privacy_fixture=dict(path=str(privacy), sha256=FIXTURE_SHA)
        ),
        maximum_native_jobs=2,
        per_job_concurrency=2,
        total_pipeline_bound=4,
        n_attempts=1,
        harbor_retry=0,
        not_part_of_new212=True,
    )
    state["long_ab8_canary"] = launch(
        "qwen35-reliability-long-ab8-native-20261103-r2.service",
        str(source),
        argv,
        admission,
        owner,
        extra,
        native_python=R / "env/harbor-reliability-r1/bin/python",
    )
    rows = []
    for tag in ["m0", "new-m2-e5"]:
        path = output / (tag + "-PROGRESS.json")
        if path.exists():
            value = base.read(path)
            rows.append(
                dict(
                    model_tag=tag,
                    path=str(path),
                    sha256=base.sha(path),
                    expected=value["expected"],
                    terminal=value["terminal"],
                    actual_agent_starts=value["actual_agent_starts"],
                    raw_results_are_not_qualified_scores=True,
                )
            )
    state["long_ab8_native_progress"] = rows


if __name__ == "__main__":
    raise SystemExit("Only the existing unique controller may admit native diagnostics")
