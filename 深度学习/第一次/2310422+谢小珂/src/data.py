import random
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset, Subset

from config import (
    DATA_DIR,
    BATCH_SIZE,
    NUM_WORKERS,
    SEED,
    VAL_SIZE,
    CIFAR10_MEAN,
    CIFAR10_STD,
)


def seed_worker(worker_id: int):
    worker_seed = SEED + worker_id
    np.random.seed(worker_seed)
    random.seed(worker_seed)


class TensorFakeCIFAR10(Dataset):
    """无需 torchvision 的快速自检数据集。真实训练仍使用 torchvision.datasets.CIFAR10。"""
    def __init__(self, size=512, seed=SEED):
        generator = torch.Generator().manual_seed(seed)
        self.images = torch.randn(size, 3, 32, 32, generator=generator)
        self.targets = torch.randint(0, 10, (size,), generator=generator)

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, idx):
        return self.images[idx], self.targets[idx]


def _import_torchvision():
    try:
        from torchvision import datasets, transforms
        return datasets, transforms
    except Exception as exc:
        raise RuntimeError(
            "torchvision 无法导入。真实 CIFAR-10 训练需要 torch 与 torchvision 版本匹配。\n"
            "建议重新安装同一 CUDA 版本的 torch/torchvision，例如按 PyTorch 官网命令安装。\n"
            f"原始错误: {exc}"
        ) from exc


def build_transforms(use_advanced_aug: bool = True):
    """训练集使用增强，验证/测试集只做确定性预处理。"""
    _, transforms = _import_torchvision()
    train_ops = [
        transforms.RandomCrop(32, padding=4),
        transforms.RandomHorizontalFlip(),
    ]

    if use_advanced_aug and hasattr(transforms, "AutoAugment") and hasattr(transforms, "AutoAugmentPolicy"):
        train_ops.append(transforms.AutoAugment(transforms.AutoAugmentPolicy.CIFAR10))

    train_ops.extend([
        transforms.ToTensor(),
        transforms.Normalize(CIFAR10_MEAN, CIFAR10_STD),
    ])

    if use_advanced_aug and hasattr(transforms, "RandomErasing"):
        train_ops.append(transforms.RandomErasing(p=0.20, scale=(0.02, 0.12), ratio=(0.3, 3.3)))

    train_transform = transforms.Compose(train_ops)
    eval_transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(CIFAR10_MEAN, CIFAR10_STD),
    ])
    return train_transform, eval_transform


def _make_fake_datasets(fast_dev_run=False):
    train_size = 256 if fast_dev_run else 5000
    val_size = 64 if fast_dev_run else 1000
    test_size = 64 if fast_dev_run else 1000
    return (
        TensorFakeCIFAR10(size=train_size, seed=SEED),
        TensorFakeCIFAR10(size=val_size, seed=SEED + 1),
        TensorFakeCIFAR10(size=test_size, seed=SEED + 2),
    )


def get_dataloaders(
    batch_size: int = BATCH_SIZE,
    num_workers: int = NUM_WORKERS,
    seed: int = SEED,
    val_size: int = VAL_SIZE,
    use_advanced_aug: bool = True,
    data_dir: str | Path = DATA_DIR,
    download: bool = True,
    use_fake_data: bool = False,
    fast_dev_run: bool = False,
):
    if use_fake_data:
        train_dataset, val_dataset, test_dataset = _make_fake_datasets(fast_dev_run)
    else:
        datasets, _ = _import_torchvision()
        train_transform, eval_transform = build_transforms(use_advanced_aug)
        data_dir = Path(data_dir)
        full_train_for_train = datasets.CIFAR10(root=str(data_dir), train=True, download=download, transform=train_transform)
        full_train_for_val = datasets.CIFAR10(root=str(data_dir), train=True, download=download, transform=eval_transform)
        test_dataset = datasets.CIFAR10(root=str(data_dir), train=False, download=download, transform=eval_transform)

        total_size = len(full_train_for_train)
        val_size = min(val_size, total_size // 5)
        generator = torch.Generator().manual_seed(seed)
        indices = torch.randperm(total_size, generator=generator).tolist()
        train_indices = indices[:-val_size]
        val_indices = indices[-val_size:]
        train_dataset = Subset(full_train_for_train, train_indices)
        val_dataset = Subset(full_train_for_val, val_indices)

    pin_memory = torch.cuda.is_available()
    common_kwargs = dict(
        num_workers=num_workers,
        pin_memory=pin_memory,
        persistent_workers=(num_workers > 0),
        worker_init_fn=seed_worker if num_workers > 0 else None,
    )

    train_generator = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, generator=train_generator, **common_kwargs)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, **common_kwargs)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, **common_kwargs)
    return train_loader, val_loader, test_loader
