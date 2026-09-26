# calcinfrasynth

cdk8s. Topology in, kubernetes manifests out.

`app.py` reads the Envoy configs from `calccontrolplane/config/` and emits the
namespace, config maps, deployments and services for the whole mesh.
