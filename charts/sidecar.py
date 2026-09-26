from imports import k8s

ENVOY_IMAGE = "envoyproxy/envoy:v1.31-latest"


def envoy_container(config_volume_name="envoy-config"):
    return k8s.Container(
        name="envoy",
        image=ENVOY_IMAGE,
        args=["-c", "/etc/envoy/envoy.yaml", "--log-level", "warn"],
        ports=[
            k8s.ContainerPort(name="proxy", container_port=9001),
            k8s.ContainerPort(name="admin", container_port=9901),
        ],
        volume_mounts=[k8s.VolumeMount(name=config_volume_name, mount_path="/etc/envoy")],
        readiness_probe=k8s.Probe(
            http_get=k8s.HttpGetAction(path="/ready", port=k8s.IntOrString.from_number(9901)),
            initial_delay_seconds=2,
            period_seconds=5,
        ),
    )


def config_volume(config_map, name="envoy-config"):
    return k8s.Volume(name=name, config_map=k8s.ConfigMapVolumeSource(name=config_map))
