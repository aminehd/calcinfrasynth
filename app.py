import argparse
from pathlib import Path

from cdk8s import App

from charts.training_job import TrainingJob


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--namespace", default="llmmesh-dev")
    p.add_argument("--image-tag", default="dev")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--out", default="../dist")
    p.add_argument("--envoy-config", default="../llmcontrolplane/config/sidecar.yaml")
    args = p.parse_args()

    envoy_path = Path(args.envoy_config)
    envoy_config = envoy_path.read_text() if envoy_path.exists() else DEFAULT_ENVOY

    app = App(outdir=args.out)
    TrainingJob(
        app,
        "llmmesh",
        namespace=args.namespace,
        image_tag=args.image_tag,
        workers=args.workers,
        envoy_config=envoy_config,
    )
    app.synth()
    print(f"synthed {args.workers} workers, tag {args.image_tag}, ns {args.namespace} -> {args.out}")


DEFAULT_ENVOY = """\
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

if __name__ == "__main__":
    main()
