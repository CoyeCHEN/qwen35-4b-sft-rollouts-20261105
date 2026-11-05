"""Validate rendered Compose without changing task execution semantics."""

from pathlib import Path
from typing import Any

import yaml

IDENTITY_LABEL = "io.harbor.remote-docker.identity"
PROJECT_LABEL = "com.docker.compose.project"


def load_compose_source(text: str) -> dict[str, Any]:
    """Precheck source only; Docker Compose remains the canonical renderer.

    Compose's standard !reset clears an inherited attribute. Accept that tag
    without teaching PyYAML any executable constructors or changing its global
    SafeLoader. Final rendered services still pass validate_compose().
    """

    class SourceLoader(yaml.SafeLoader):
        pass

    SourceLoader.add_constructor("!reset", lambda loader, node: None)
    return yaml.load(text, Loader=SourceLoader) or {}


def validate_compose(
    document: dict[str, Any], project: str, roots: list[Path]
) -> dict[Path, list[dict[str, Any]]]:
    if document.get("name") != project or "main" not in document.get("services", {}):
        raise ValueError("Expected the owned Compose project and a main service")
    if document.get("configs") or document.get("secrets"):
        raise ValueError("Remote Docker does not support Compose configs/secrets")
    for kind in ("volumes", "networks"):
        for name, spec in document.get(kind, {}).items():
            spec = spec or {}
            if (
                spec.get("external")
                or spec.get("driver_opts")
                or spec.get("driver")
                not in (None, "local" if kind == "volumes" else "bridge")
                or spec.get("name", f"{project}_{name}") != f"{project}_{name}"
            ):
                raise ValueError(
                    "Remote Docker requires project-scoped volumes/networks"
                )
    binds: dict[Path, list[dict[str, Any]]] = {}

    def local_input(value: str) -> Path:
        source = Path(value).resolve()
        if not source.exists() or not any(
            source.is_relative_to(root) for root in roots
        ):
            raise ValueError(
                "Remote input is outside declared task/Compose directories"
            )
        return source

    for name, service in document["services"].items():
        for field in (
            "privileged",
            "container_name",
            "devices",
            "device_cgroup_rules",
            "cgroup_parent",
            "volumes_from",
            "ports",
            "use_api_socket",
            "develop",
            "provider",
            "post_start",
            "pre_stop",
            "cap_add",
            "gpus",
            "runtime",
            "uts",
            "userns_mode",
            "cgroup",
            "pid",
            "ipc",
        ):
            if service.get(field):
                raise ValueError(
                    f"Remote Docker does not support service option {field}: {name}"
                )
        if any(
            option not in ("no-new-privileges", "no-new-privileges:true")
            for option in service.get("security_opt", [])
        ):
            raise ValueError(
                "Remote Docker only supports restrictive no-new-privileges security options"
            )
        mode = service.get("network_mode", "")
        if mode and mode not in ("none", "bridge") and not mode.startswith("service:"):
            raise ValueError("Remote Docker rejects host/external container networking")
        deploy = service.get("deploy", {})
        if deploy.get("replicas", 1) != 1 or deploy.get("resources", {}).get(
            "reservations", {}
        ).get("devices"):
            raise ValueError(
                "Remote Docker does not support replicas or device reservations"
            )
        build = service.get("build")
        if isinstance(build, dict):
            if any(
                build.get(k) for k in ("privileged", "entitlements", "ssh", "secrets")
            ) or build.get("network") not in (None, "default", "none"):
                raise ValueError("Remote Docker rejects privileged/host build options")
            context = local_input(build["context"])
            if build.get("dockerfile"):
                dockerfile = (context / build["dockerfile"]).resolve()
                if not dockerfile.is_relative_to(context) or not dockerfile.is_file():
                    raise ValueError("Dockerfile must be inside its build context")
            for value in build.get("additional_contexts", {}).values():
                if not value.startswith(("service:", "docker-image:")):
                    local_input(value)
        for mount in service.get("volumes", []):
            if mount["type"] == "bind":
                if mount.get("bind", {}).get("propagation", "rprivate") not in (
                    "private",
                    "rprivate",
                ):
                    raise ValueError("Remote bind propagation must remain private")
                original = Path(mount["source"])
                source = local_input(mount["source"])
                if original.is_symlink() or source.is_socket():
                    raise ValueError("Remote bind source cannot be a symlink or socket")
                binds.setdefault(source, []).append(mount)
            elif mount["type"] not in ("volume", "tmpfs"):
                raise ValueError("Unsupported remote volume type")
    return binds


def label_resources(document: dict[str, Any], identity: str) -> None:
    for kind in ("services", "networks", "volumes"):
        for name, spec in document.get(kind, {}).items():
            spec = spec or {}
            document[kind][name] = spec
            spec.setdefault("labels", {})[IDENTITY_LABEL] = identity
