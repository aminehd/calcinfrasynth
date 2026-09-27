# calcinfrasynth

cdk8s. Topology in, kubernetes manifests out.

`app.py` reads the Envoy configs from `calcnetworking/config/` and emits the
namespace, config maps, deployments and services for the whole mesh into `dist/`.
Nothing is hand-written yaml, and `dist/` is generated, never committed here.

```
python app.py --namespace calcmesh-dev --image-tag dev --out ../dist
```

`charts/calc_job.py` is the topology: each calculator is an app container plus an
ingress Envoy, and the coordinator is an app container plus an egress Envoy plus
the syncer that feeds it xDS. `charts/sidecar.py` builds those sidecars.

`python -m pytest tests` asserts the shape of the output: which deployments
exist, which containers are in each pod, that the syncer and Envoy share the xDS
`emptyDir`, and that the coordinator is the only NodePort.
