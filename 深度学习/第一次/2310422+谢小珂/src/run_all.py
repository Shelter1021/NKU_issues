import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_MODELS = ["original", "resnet", "densenet", "mobilenet", "res2net"]


def main():
    parser = argparse.ArgumentParser(description="Run all CIFAR-10 CNN lab experiments.")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS, choices=DEFAULT_MODELS)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--batch_size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=0.05)
    parser.add_argument("--num_workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--data_dir", type=str, default=None)
    parser.add_argument("--output_dir", type=str, default=None)
    parser.add_argument("--basic_aug", action="store_true")
    parser.add_argument("--amp", action="store_true")
    parser.add_argument("--no_amp", action="store_true")
    parser.add_argument("--no_download", action="store_true")
    parser.add_argument("--use_fake_data", action="store_true")
    parser.add_argument("--fast_dev_run", action="store_true")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    train_script = project_root / "src" / "train.py"

    for model in args.models:
        print("=" * 88)
        print(f"Running model: {model}")
        print("=" * 88)
        cmd = [
            sys.executable,
            str(train_script),
            "--model", model,
            "--epochs", str(args.epochs),
            "--batch_size", str(args.batch_size),
            "--lr", str(args.lr),
            "--num_workers", str(args.num_workers),
            "--seed", str(args.seed),
        ]
        if args.data_dir:
            cmd += ["--data_dir", args.data_dir]
        if args.output_dir:
            cmd += ["--output_dir", args.output_dir]
        for flag in ["basic_aug", "amp", "no_amp", "no_download", "use_fake_data", "fast_dev_run"]:
            if getattr(args, flag):
                cmd.append("--" + flag)
        subprocess.run(cmd, check=True)

    print("=" * 88)
    print("All experiments finished. Run: python src/report_assets.py --output_dir outputs")
    print("=" * 88)


if __name__ == "__main__":
    main()
