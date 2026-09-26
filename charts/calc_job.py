from cdk8s import Chart
from imports import k8s

from charts.sidecar import config_volume, envoy_container

COORDINATOR_CONFIG_MAP = "envoy-coordinator"
SERVICE_CONFIG_MAP = "envoy-service"
COORDINATOR_NODE_PORT = 30000
APP_PORT = 8081


class CalcMesh(Chart):
    def __init__(self, scope, id, *, namespace, image_tag, worker_envoy, coordinator_envoy):
        super().__init__(scope, id, namespace=namespace)
        self.ns = namespace

        k8s.KubeNamespace(
            self,
            "namespace",
            metadata=k8s.ObjectMeta(name=namespace, labels=self._labels("namespace")),
        )

        self._config_map("coordinator-envoy-config", COORDINATOR_CONFIG_MAP, worker_envoy)
        self._config_map("service-envoy-config", SERVICE_CONFIG_MAP, coordinator_envoy)


        for calc in ("adder", "multiplier"):
            self._service(calc, 8080)
            self._deployment(
                calc,
                f"{calc}:{image_tag}",
                replicas=1,
                port=APP_PORT,
                sidecar=SERVICE_CONFIG_MAP,
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
            env={
                "PORT": str(APP_PORT),
                "CALC_URL": "http://127.0.0.1:9001",
                "CONTROL_PLANE_URL": "http://controlplane:18000",
            },
        )

        self._service("controlplane", 18000)
        self._deployment("controlplane", f"controlplane:{image_tag}", replicas=1, port=18000)


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

    def _deployment(self, name, image, *, replicas, port, sidecar=None, sidecar_port=None, env=None):
        containers = [
            k8s.Container(
                name=name,
                image=image,
                image_pull_policy="IfNotPresent",
                ports=[k8s.ContainerPort(container_port=port)],
                env=[k8s.EnvVar(name=k, value=v) for k, v in (env or {}).items()],
            )
        ]
        volumes = []
        if sidecar:
            containers.append(envoy_container(sidecar_port))
            volumes.append(config_volume(sidecar))

        k8s.KubeDeployment(
            self,
            f"{name}-deployment",
            metadata=k8s.ObjectMeta(name=name, namespace=self.ns, labels=self._labels(name)),
            spec=k8s.DeploymentSpec(
                replicas=replicas,
                selector=k8s.LabelSelector(match_labels=self._labels(name)),
                template=k8s.PodTemplateSpec(
                    metadata=k8s.ObjectMeta(labels=self._labels(name)),
                    spec=k8s.PodSpec(containers=containers, volumes=volumes or None),
                ),
            ),
        )

    def _service(self, name, port, node_port=None):
        k8s.KubeService(
            self,
            f"{name}-service",
            metadata=k8s.ObjectMeta(name=name, namespace=self.ns, labels=self._labels(name)),
            spec=k8s.ServiceSpec(
                type="NodePort" if node_port else None,
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
