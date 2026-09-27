from cdk8s import Chart
from imports import k8s

from charts.sidecar import (
    config_volume,
    envoy_container,
    syncer_container,
    xds_seed_container,
    xds_volume,
)

COORDINATOR_CONFIG_MAP = "envoy-coordinator"
CALCULATOR_CONFIG_MAP = "envoy-calculator"
SERVICES_CONFIG_MAP = "services-config"
COORDINATOR_NODE_PORT = 30000
APP_PORT = 8081


def calculators(services):
    names, current = [], None
    for raw in services.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            current = line.rstrip(":")
        elif current and line.strip().startswith("op:"):
            names.append(current)
    return names


class CalcMesh(Chart):
    def __init__(self, scope, id, *, namespace, image_tag, coordinator_bootstrap, calculator_envoy, lds, cds, services):
        super().__init__(scope, id, namespace=namespace)
        self.ns = namespace
        self.image_tag = image_tag

        k8s.KubeNamespace(
            self,
            "namespace",
            metadata=k8s.ObjectMeta(name=namespace, labels=self._labels("namespace")),
        )

        k8s.KubeConfigMap(
            self,
            "coordinator-envoy-config",
            metadata=k8s.ObjectMeta(name=COORDINATOR_CONFIG_MAP, namespace=namespace),
            data={"envoy.yaml": coordinator_bootstrap, "lds.yaml": lds, "cds.yaml": cds},
        )
        self._config_map("calculator-envoy-config", CALCULATOR_CONFIG_MAP, calculator_envoy)
        k8s.KubeConfigMap(
            self,
            "services-config",
            metadata=k8s.ObjectMeta(name=SERVICES_CONFIG_MAP, namespace=namespace),
            data={"services.yaml": services},
        )

        for calc in calculators(services):
            self._service(calc, 8080, headless=True)
            self._deployment(
                calc,
                f"{calc}:{image_tag}",
                replicas=1,
                port=APP_PORT,
                sidecar=CALCULATOR_CONFIG_MAP,
                sidecar_port=8080,
                env={"PORT": str(APP_PORT)},
            )

        self._service("coordinator", APP_PORT, node_port=COORDINATOR_NODE_PORT)
        self._deployment(
            "coordinator",
            f"coordinator:{image_tag}",
            replicas=1,
            port=APP_PORT,
            sidecar=COORDINATOR_CONFIG_MAP,
            sidecar_port=9001,
            xds=True,
            env={"PORT": str(APP_PORT), "CALC_URL": "http://127.0.0.1:9001"},
        )

        self._service("extproc", 18001)
        self._deployment(
            "extproc",
            f"controlplane:{image_tag}",
            replicas=1,
            port=18001,
            command=["python", "-u", "src/cmd/extproc.py"],
        )

        self._service("controlplane", 18000)
        self._deployment(
            "controlplane",
            f"controlplane:{image_tag}",
            replicas=1,
            port=18000,
            env={"SERVICES_FILE": "/etc/calcmesh/services.yaml"},
            mount=(SERVICES_CONFIG_MAP, "/etc/calcmesh"),
        )


    def _labels(self, component):
        return {
            "app.kubernetes.io/name": component,
            "app.kubernetes.io/part-of": "calcmesh",
        }

    def _config_map(self, id, name, body):
        k8s.KubeConfigMap(
            self,
            id,
            metadata=k8s.ObjectMeta(name=name, namespace=self.ns),
            data={"envoy.yaml": body},
        )

    def _deployment(self, name, image, *, replicas, port, sidecar=None, sidecar_port=None, env=None, xds=False, mount=None, command=None):
        volumes = []
        mounts = []
        if mount:
            config_map, path = mount
            mounts.append(k8s.VolumeMount(name="services", mount_path=path))
            volumes.append(
                k8s.Volume(name="services", config_map=k8s.ConfigMapVolumeSource(name=config_map))
            )

        containers = [
            k8s.Container(
                name=name,
                image=image,
                image_pull_policy="IfNotPresent",
                command=command,
                ports=[k8s.ContainerPort(container_port=port)],
                env=[k8s.EnvVar(name=k, value=v) for k, v in (env or {}).items()],
                volume_mounts=mounts or None,
            )
        ]
        if sidecar:
            containers.append(envoy_container(sidecar_port, xds=xds))
            volumes.append(config_volume(sidecar))
        init_containers = []
        if xds:
            containers.append(syncer_container(f"controlplane:{self.image_tag}"))
            volumes.append(xds_volume())
            init_containers.append(xds_seed_container())

        k8s.KubeDeployment(
            self,
            f"{name}-deployment",
            metadata=k8s.ObjectMeta(name=name, namespace=self.ns, labels=self._labels(name)),
            spec=k8s.DeploymentSpec(
                replicas=replicas,
                selector=k8s.LabelSelector(match_labels=self._labels(name)),
                template=k8s.PodTemplateSpec(
                    metadata=k8s.ObjectMeta(labels=self._labels(name)),
                    spec=k8s.PodSpec(
                        init_containers=init_containers or None,
                        containers=containers,
                        volumes=volumes or None,
                    ),
                ),
            ),
        )

    def _service(self, name, port, node_port=None, headless=False):
        k8s.KubeService(
            self,
            f"{name}-service",
            metadata=k8s.ObjectMeta(name=name, namespace=self.ns, labels=self._labels(name)),
            spec=k8s.ServiceSpec(
                type="NodePort" if node_port else None,
                cluster_ip="None" if headless else None,
                selector=self._labels(name),
                ports=[
                    k8s.ServicePort(
                        port=port,
                        target_port=k8s.IntOrString.from_number(port),
                        node_port=node_port,
                        name="http",
                    )
                ],
            ),
        )
