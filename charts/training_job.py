from cdk8s import Chart
from imports import k8s

from charts.sidecar import config_volume, envoy_container

ENVOY_CONFIG_MAP = "envoy-sidecar"


class TrainingJob(Chart):
    def __init__(self, scope, id, *, namespace, image_tag, workers, envoy_config):
        super().__init__(scope, id, namespace=namespace)
        self.ns = namespace

        k8s.KubeNamespace(
            self,
            "namespace",
            metadata=k8s.ObjectMeta(name=namespace, labels=self._labels("namespace")),
        )

        k8s.KubeConfigMap(
            self,
            "envoy-config",
            metadata=k8s.ObjectMeta(name=ENVOY_CONFIG_MAP, namespace=namespace),
            data={"envoy.yaml": envoy_config},
        )

        self._service("coordinator", 8080)
        self._deployment("coordinator", f"coordinator:{image_tag}", replicas=1, port=8080)

        self._service("controlplane", 18000)
        self._deployment("controlplane", f"controlplane:{image_tag}", replicas=1, port=18000)

        self._service("worker", 8081)
        self._deployment(
            "worker",
            f"worker:{image_tag}",
            replicas=workers,
            port=8081,
            sidecar=True,
            env={"COORDINATOR_URL": "http://127.0.0.1:9001"},
        )

    def _labels(self, component):
        return {
            "app.kubernetes.io/name": component,
            "app.kubernetes.io/part-of": "llmmesh",
        }

    def _deployment(self, name, image, *, replicas, port, sidecar=False, env=None):
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
            containers.append(envoy_container())
            volumes.append(config_volume(ENVOY_CONFIG_MAP))

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

    def _service(self, name, port):
        k8s.KubeService(
            self,
            f"{name}-service",
            metadata=k8s.ObjectMeta(name=name, namespace=self.ns, labels=self._labels(name)),
            spec=k8s.ServiceSpec(
                selector=self._labels(name),
                ports=[k8s.ServicePort(port=port, target_port=k8s.IntOrString.from_number(port), name="http")],
            ),
        )
