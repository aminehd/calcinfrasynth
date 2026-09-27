import argparse
from pathlib import Path

from cdk8s import App

from charts.calc_job import CalcMesh

CONFIG = "../calccontrolplane/config"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--namespace", default="calcmesh-dev")
    p.add_argument("--image-tag", default="dev")
    p.add_argument("--out", default="../dist")
    p.add_argument("--coordinator-bootstrap", default=f"{CONFIG}/coordinator/bootstrap.yaml")
    p.add_argument("--lds", default=f"{CONFIG}/coordinator/lds.yaml")
    p.add_argument("--cds", default=f"{CONFIG}/coordinator/cds.yaml")
    p.add_argument("--calculator-envoy", default=f"{CONFIG}/calculator/envoy.yaml")
    p.add_argument("--services", default=f"{CONFIG}/services.yaml")
    args = p.parse_args()

    app = App(outdir=args.out)
    CalcMesh(
        app,
        "calcmesh",
        namespace=args.namespace,
        image_tag=args.image_tag,
        coordinator_bootstrap=Path(args.coordinator_bootstrap).read_text(),
        calculator_envoy=Path(args.calculator_envoy).read_text(),
        lds=Path(args.lds).read_text(),
        cds=Path(args.cds).read_text(),
        services=Path(args.services).read_text(),
    )
    app.synth()
    print(f"synthed tag {args.image_tag}, ns {args.namespace} -> {args.out}")


if __name__ == "__main__":
    main()
