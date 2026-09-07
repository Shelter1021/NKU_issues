#!/usr/bin/env bash
set -e
python run_experiment.py --epochs 50 --hidden-size 128 --batch-size 128 --torch-threads 1
