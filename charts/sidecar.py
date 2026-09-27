from imports import k8s

ENVOY_IMAGE = "envoyproxy/envoy:v1.31-latest"
VOLUME_NAME = "envoy-config"


XDS_VOLUME = "xds"


def syncer_container(image):
    return k8s.Container(
        name="syncer",
        image=image,
        image_pull_policy="IfNotPresent",
        command=["python", "-u", "src/cmd/syncer.py"],
        env=[
            k8s.EnvVar(name="CONTROL_PLANE_URL", value="http://controlplane:18000"),
            k8s.EnvVar(name="XDS_DIR", value="/etc/envoy/xds"),
        ],
        volume_mounts=[k8s.VolumeMount(name=XDS_VOLUME, mount_path="/etc/envoy/xds")],
    )


def xds_seed_container():
    return k8s.Container(
        name="xds-seed",
        image=ENVOY_IMAGE,
        command=["sh", "-c", "cp /seed/lds.yaml /seed/cds.yaml /etc/envoy/xds/"],
        volume_mounts=[
            k8s.VolumeMount(name=VOLUME_NAME, mount_path="/seed"),
            k8s.VolumeMount(name=XDS_VOLUME, mount_path="/etc/envoy/xds"),
        ],
    )


def xds_volume():
    return k8s.Volume(name=XDS_VOLUME, empty_dir=k8s.EmptyDirVolumeSource())


def envoy_container(proxy_port, xds=False):
    return k8s.Container(
        name="envoy",
        image=ENVOY_IMAGE,
        args=["-c", "/etc/envoy/envoy.yaml", "--log-level", "warn"],
        ports=[
            k8s.ContainerPort(name="proxy", container_port=proxy_port),
            k8s.ContainerPort(name="admin", container_port=9901),
        ],
        volume_mounts=(
            [k8s.VolumeMount(name=VOLUME_NAME, mount_path="/etc/envoy")]
            + ([k8s.VolumeMount(name=XDS_VOLUME, mount_path="/etc/envoy/xds")] if xds else [])
        ),
        readiness_probe=k8s.Probe(
            http_get=k8s.HttpGetAction(path="/ready", port=k8s.IntOrString.from_number(9901)),
            initial_delay_seconds=2,
            period_seconds=5,
        ),
    )


def config_volume(config_map):
    return k8s.Volume(name=VOLUME_NAME, config_map=k8s.ConfigMapVolumeSource(name=config_map))
