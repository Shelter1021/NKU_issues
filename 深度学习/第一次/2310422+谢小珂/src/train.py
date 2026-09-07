import argparse
import time
from pathlib import Path
from contextlib import nullcontext

import torch
import torch.nn as nn
import torch.optim as optim
from tqdm import tqdm

from config import (
    OUTPUT_DIR,
    DATA_DIR,
    SEED,
    BATCH_SIZE,
    EPOCHS,
    LR,
    MOMENTUM,
    WEIGHT_DECAY,
    LABEL_SMOOTHING,
    WARMUP_EPOCHS,
)
from data import get_dataloaders
from models import get_model
from utils import (
    set_seed,
    ensure_dir,
    count_parameters,
    accuracy,
    AverageMeter,
    save_model_structure,
    save_metrics_csv,
    save_json,
    plot_curves,
    update_summary,
    format_time,
    current_time,
)


def get_amp_context(device, enabled):
    if enabled and device.type == "cuda":
        return torch.amp.autocast(device_type="cuda")
    return nullcontext()


def train_one_epoch(model, loader, criterion, optimizer, device, scaler=None, amp_enabled=False):
    model.train()
    loss_meter = AverageMeter()
    acc_meter = AverageMeter()
    pbar = tqdm(loader, desc="Training", leave=False)

    for images, targets in pbar:
        images = images.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)

        with get_amp_context(device, amp_enabled):
            outputs = model(images)
            loss = criterion(outputs, targets)

        if scaler is not None:
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            optimizer.step()

        batch_size = images.size(0)
        loss_meter.update(loss.item(), batch_size)
        acc_meter.update(accuracy(outputs.detach(), targets), batch_size)
        pbar.set_postfix({"loss": f"{loss_meter.avg:.4f}", "acc": f"{acc_meter.avg:.4f}"})

    return loss_meter.avg, acc_meter.avg


@torch.no_grad()
def evaluate(model, loader, criterion, device, desc="Evaluating"):
    model.eval()
    loss_meter = AverageMeter()
    acc_meter = AverageMeter()
    pbar = tqdm(loader, desc=desc, leave=False)

    for images, targets in pbar:
        images = images.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)
        outputs = model(images)
        loss = criterion(outputs, targets)
        batch_size = images.size(0)
        loss_meter.update(loss.item(), batch_size)
        acc_meter.update(accuracy(outputs, targets), batch_size)
        pbar.set_postfix({"loss": f"{loss_meter.avg:.4f}", "acc": f"{acc_meter.avg:.4f}"})

    return loss_meter.avg, acc_meter.avg


def build_scheduler(optimizer, epochs, warmup_epochs):
    warmup_epochs = min(max(warmup_epochs, 0), max(epochs - 1, 0))
    if warmup_epochs == 0:
        return optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    warmup = optim.lr_scheduler.LinearLR(optimizer, start_factor=0.1, total_iters=warmup_epochs)
    cosine = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs - warmup_epochs)
    return optim.lr_scheduler.SequentialLR(optimizer, schedulers=[warmup, cosine], milestones=[warmup_epochs])


def parse_args():
    parser = argparse.ArgumentParser(description="Train CIFAR-10 CNN models for the course lab.")
    parser.add_argument("--model", type=str, default="original", choices=["original", "resnet", "densenet", "mobilenet", "res2net"])
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--batch_size", type=int, default=BATCH_SIZE)
    parser.add_argument("--lr", type=float, default=LR)
    parser.add_argument("--momentum", type=float, default=MOMENTUM)
    parser.add_argument("--weight_decay", type=float, default=WEIGHT_DECAY)
    parser.add_argument("--label_smoothing", type=float, default=LABEL_SMOOTHING)
    parser.add_argument("--warmup_epochs", type=int, default=WARMUP_EPOCHS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--num_workers", type=int, default=2)
    parser.add_argument("--data_dir", type=str, default=str(DATA_DIR))
    parser.add_argument("--output_dir", type=str, default=str(OUTPUT_DIR))
    parser.add_argument("--no_download", action="store_true")
    parser.add_argument("--basic_aug", action="store_true", help="Disable AutoAugment and RandomErasing.")
    parser.add_argument("--amp", action="store_true", help="Use CUDA mixed precision.")
    parser.add_argument("--no_amp", action="store_true", help="Explicitly disable AMP.")
    parser.add_argument("--use_fake_data", action="store_true", help="Use torchvision FakeData for smoke testing.")
    parser.add_argument("--fast_dev_run", action="store_true", help="Small fake-data smoke test mode.")
    return parser.parse_args()


def main():
    args = parse_args()
    set_seed(args.seed)
    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp_enabled = bool(args.amp and not args.no_amp and device.type == "cuda")

    print("=" * 88)
    print(f"Start time: {current_time()}")
    print(f"Model: {args.model}")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Epochs: {args.epochs} | Batch size: {args.batch_size} | LR: {args.lr} | AMP: {amp_enabled}")
    print("=" * 88)

    train_loader, val_loader, test_loader = get_dataloaders(
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        seed=args.seed,
        use_advanced_aug=(not args.basic_aug),
        data_dir=args.data_dir,
        download=(not args.no_download),
        use_fake_data=args.use_fake_data,
        fast_dev_run=args.fast_dev_run,
    )

    model = get_model(args.model).to(device)
    model_name = model.__class__.__name__
    num_params = count_parameters(model)
    model_dir = output_dir / model_name
    ensure_dir(model_dir)

    paths = {
        "structure": model_dir / f"{model_name}_structure.txt",
        "metrics": model_dir / f"{model_name}_metrics.csv",
        "curves": model_dir / f"{model_name}_curves.png",
        "best": model_dir / f"{model_name}_best.pth",
        "last": model_dir / f"{model_name}_last.pth",
        "test_result": model_dir / f"{model_name}_test_result.json",
        "config": model_dir / f"{model_name}_config.json",
    }

    print(model)
    print(f"Trainable parameters: {num_params:,}")
    save_model_structure(model, paths["structure"])
    save_json({"args": vars(args), "model_name": model_name, "num_params": num_params}, paths["config"])

    criterion = nn.CrossEntropyLoss(label_smoothing=args.label_smoothing)
    optimizer = optim.SGD(
        model.parameters(),
        lr=args.lr,
        momentum=args.momentum,
        weight_decay=args.weight_decay,
        nesterov=True,
    )
    scheduler = build_scheduler(optimizer, args.epochs, args.warmup_epochs)
    scaler = torch.amp.GradScaler("cuda") if amp_enabled else None

    history = []
    best_val_acc = 0.0
    best_val_loss = float("inf")
    best_epoch = 0
    total_start = time.time()

    for epoch in range(1, args.epochs + 1):
        epoch_start = time.time()
        train_loss, train_acc = train_one_epoch(model, train_loader, criterion, optimizer, device, scaler, amp_enabled)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device, desc="Validating")
        scheduler.step()
        current_lr = optimizer.param_groups[0]["lr"]
        epoch_time = time.time() - epoch_start
        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "train_acc": train_acc,
            "val_loss": val_loss,
            "val_acc": val_acc,
            "lr": current_lr,
            "time_sec": epoch_time,
        }
        history.append(row)
        save_metrics_csv(history, paths["metrics"])
        plot_curves(history, paths["curves"], model_name)

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_val_loss = val_loss
            best_epoch = epoch
            torch.save({
                "model_name": model_name,
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "best_val_acc": best_val_acc,
                "best_val_loss": best_val_loss,
                "num_params": num_params,
                "args": vars(args),
            }, paths["best"])

        torch.save({
            "model_name": model_name,
            "model_state_dict": model.state_dict(),
            "epoch": epoch,
            "val_acc": val_acc,
            "num_params": num_params,
            "args": vars(args),
        }, paths["last"])

        print(
            f"Epoch [{epoch:03d}/{args.epochs:03d}] "
            f"Train Loss: {train_loss:.4f} | Train Acc: {train_acc:.4f} | "
            f"Val Loss: {val_loss:.4f} | Val Acc: {val_acc:.4f} | "
            f"Best Val Acc: {best_val_acc:.4f} @ Epoch {best_epoch} | "
            f"LR: {current_lr:.6f} | Time: {format_time(epoch_time)}"
        )

    checkpoint = torch.load(paths["best"], map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])
    test_loss, test_acc = evaluate(model, test_loader, criterion, device, desc="Testing")
    total_time = time.time() - total_start

    test_result = {
        "model": model_name,
        "params": num_params,
        "epochs": args.epochs,
        "best_epoch": best_epoch,
        "best_val_acc": best_val_acc,
        "best_val_loss": best_val_loss,
        "test_acc": test_acc,
        "test_loss": test_loss,
        "total_time": format_time(total_time),
    }
    save_json(test_result, paths["test_result"])
    update_summary(output_dir / "summary.csv", test_result)

    print("=" * 88)
    print(f"Finished model: {model_name}")
    print(f"Best Val Acc: {best_val_acc:.4f} at epoch {best_epoch}")
    print(f"Test Acc: {test_acc:.4f}")
    print(f"Outputs saved to: {model_dir}")
    print(f"Total time: {format_time(total_time)}")
    print("=" * 88)


if __name__ == "__main__":
    main()
