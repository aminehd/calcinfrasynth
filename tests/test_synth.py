import sys
from pathlib import Path

import pytest
from cdk8s import Testing as cdk8s_testing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from charts.calc_job import CalcMesh

CONFIG = ROOT.parent / "calccontrolplane" / "config"


@pytest.fixture(scope="module")
def manifest():
    chart = CalcMesh(
        cdk8s_testing.app(),
        "calcmesh",
        namespace="calcmesh-test",
        image_tag="test",
        coordinator_bootstrap=(CONFIG / "coordinator" / "bootstrap.yaml").read_text(),
        calculator_envoy=(CONFIG / "calculator" / "envoy.yaml").read_text(),
        lds=(CONFIG / "coordinator" / "lds.yaml").read_text(),
        cds=(CONFIG / "coordinator" / "cds.yaml").read_text(),
        services=(CONFIG / "services.yaml").read_text(),
    )
    return cdk8s_testing.synth(chart)


def of_kind(manifest, kind):
    return {o["metadata"]["name"]: o for o in manifest if o["kind"] == kind}


def test_every_object_lands_in_the_namespace(manifest):
    for obj in manifest:
        if obj["kind"] == "Namespace":
            assert obj["metadata"]["name"] == "calcmesh-test"
        else:
            assert obj["metadata"]["namespace"] == "calcmesh-test", obj["metadata"]["name"]


def test_the_expected_deployments_exist(manifest):
    assert set(of_kind(manifest, "Deployment")) == {
        "adder",
        "multiplier",
        "coordinator",
        "extproc",
        "controlplane",
    }


def test_calculators_get_an_ingress_sidecar(manifest):
    for name in ("adder", "multiplier"):
        pod = of_kind(manifest, "Deployment")[name]["spec"]["template"]["spec"]
        names = [c["name"] for c in pod["containers"]]
        assert names == [name, "envoy"]
        envoy = pod["containers"][1]
        assert envoy["ports"][0]["containerPort"] == 8080
        assert {v["name"] for v in pod["volumes"]} == {"envoy-config"}


def test_coordinator_gets_an_egress_sidecar_and_a_syncer(manifest):
    pod = of_kind(manifest, "Deployment")["coordinator"]["spec"]["template"]["spec"]
    assert [c["name"] for c in pod["containers"]] == ["coordinator", "envoy", "syncer"]
    envoy = pod["containers"][1]
    assert envoy["ports"][0]["containerPort"] == 9001
    assert {v["name"] for v in pod["volumes"]} == {"envoy-config", "xds"}


def test_syncer_and_envoy_share_the_xds_emptydir(manifest):
    pod = of_kind(manifest, "Deployment")["coordinator"]["spec"]["template"]["spec"]
    xds = [v for v in pod["volumes"] if v["name"] == "xds"][0]
    assert "emptyDir" in xds
    for container in pod["containers"][1:]:
        paths = [m["mountPath"] for m in container["volumeMounts"]]
        assert "/etc/envoy/xds" in paths


def test_coordinator_talks_to_its_own_sidecar(manifest):
    app = of_kind(manifest, "Deployment")["coordinator"]["spec"]["template"]["spec"]["containers"][0]
    env = {e["name"]: e["value"] for e in app["env"]}
    assert env["CALC_URL"] == "http://127.0.0.1:9001"


def test_coordinator_is_the_only_nodeport(manifest):
    services = of_kind(manifest, "Service")
    exposed = {n: s for n, s in services.items() if s["spec"].get("type") == "NodePort"}
    assert list(exposed) == ["coordinator"]
    assert exposed["coordinator"]["spec"]["ports"][0]["nodePort"] == 30000


def test_control_plane_reads_the_mounted_services_file(manifest):
    app = of_kind(manifest, "Deployment")["controlplane"]["spec"]["template"]["spec"]
    env = {e["name"]: e["value"] for e in app["containers"][0]["env"]}
    assert env["SERVICES_FILE"] == "/etc/calcmesh/services.yaml"
    assert app["containers"][0]["volumeMounts"][0]["mountPath"] == "/etc/calcmesh"


def test_extproc_runs_the_ext_proc_server(manifest):
    pod = of_kind(manifest, "Deployment")["extproc"]["spec"]["template"]["spec"]
    assert pod["containers"][0]["command"] == ["python", "-u", "src/extproc.py"]
    assert pod["containers"][0]["ports"][0]["containerPort"] == 18001


def test_coordinator_config_map_carries_the_xds_files(manifest):
    data = of_kind(manifest, "ConfigMap")["envoy-coordinator"]["data"]
    assert set(data) == {"envoy.yaml", "lds.yaml", "cds.yaml"}
    assert "dynamic_resources" in data["envoy.yaml"]


def test_an_init_container_seeds_the_xds_dir_before_envoy_starts(manifest):
    pod = of_kind(manifest, "Deployment")["coordinator"]["spec"]["template"]["spec"]
    seed = pod["initContainers"][0]
    assert seed["name"] == "xds-seed"
    assert "/etc/envoy/xds/" in seed["command"][-1]
    assert {m["mountPath"] for m in seed["volumeMounts"]} == {"/seed", "/etc/envoy/xds"}


def test_calculators_need_no_init_container(manifest):
    for name in ("adder", "multiplier"):
        pod = of_kind(manifest, "Deployment")[name]["spec"]["template"]["spec"]
        assert "initContainers" not in pod
