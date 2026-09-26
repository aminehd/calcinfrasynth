import argparse
from pathlib import Path

from cdk8s import App

from charts.calc_job import CalcMesh


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--namespace", default="calcmesh-dev")
    p.add_argument("--image-tag", default="dev")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--out", default="../dist")
    p.add_argument("--worker-envoy", default="../calccontrolplane/config/sidecar-worker.yaml")
    p.add_argument("--coordinator-envoy", default="../calccontrolplane/config/sidecar-coordinator.yaml")
    args = p.parse_args()

    worker_path = Path(args.worker_envoy)
    coordinator_path = Path(args.coordinator_envoy)
    worker_envoy = worker_path.read_text() if worker_path.exists() else DEFAULT_WORKER_ENVOY
    coordinator_envoy = (
        coordinator_path.read_text() if coordinator_path.exists() else DEFAULT_COORDINATOR_ENVOY
    )

    app = App(outdir=args.out)
    CalcMesh(
        app,
        "calcmesh",
        namespace=args.namespace,
        image_tag=args.image_tag,
        workers=args.workers,
        worker_envoy=worker_envoy,
        coordinator_envoy=coordinator_envoy,
    )
    app.synth()
    print(f"synthed {args.workers} workers, tag {args.image_tag}, ns {args.namespace} -> {args.out}")


DEFAULT_WORKER_ENVOY = """\
admin:
  address: { socket_address: { address: 0.0.0.0, port_value: 9901 } }
static_resources:
  listeners:
    - name: to_coordinator
      address: { socket_address: { address: 127.0.0.1, port_value: 9001 } }
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
                stat_prefix: egress
                route_config:
                  name: local
                  virtual_hosts:
                    - name: coordinator
                      domains: ["*"]
                      routes:
                        - match: { prefix: "/" }
                          route: { cluster: coordinator, timeout: 5s }
                http_filters:
                  - name: envoy.filters.http.router
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
  clusters:
    - name: coordinator
      type: STRICT_DNS
      lb_policy: ROUND_ROBIN
      connect_timeout: 1s
      load_assignment:
        cluster_name: coordinator
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address: { address: coordinator, port_value: 8080 }
"""

DEFAULT_COORDINATOR_ENVOY = """\
admin:
  address: { socket_address: { address: 0.0.0.0, port_value: 9901 } }
static_resources:
  listeners:
    - name: inbound
      address: { socket_address: { address: 0.0.0.0, port_value: 8080 } }
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
                stat_prefix: ingress
                route_config:
                  name: local
                  virtual_hosts:
                    - name: app
                      domains: ["*"]
                      routes:
                        - match: { prefix: "/" }
                          route: { cluster: app, timeout: 5s }
                http_filters:
                  - name: envoy.filters.http.router
                    typed_config:
                      "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
  clusters:
    - name: app
      type: STATIC
      connect_timeout: 1s
      load_assignment:
        cluster_name: app
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address: { address: 127.0.0.1, port_value: 8081 }
"""

if __name__ == "__main__":
    main()
