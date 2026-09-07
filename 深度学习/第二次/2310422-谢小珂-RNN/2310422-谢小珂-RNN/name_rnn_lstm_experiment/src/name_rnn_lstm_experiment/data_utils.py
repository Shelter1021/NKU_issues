from __future__ import annotations

import csv
import json
import random
import string
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import torch
from torch.utils.data import Dataset

# The character table is kept consistent with the teacher's CharRNN tutorial.
# "_" is reserved for rare characters outside the table.
ALLOWED_CHARACTERS = string.ascii_letters + " .,;'" + "_"
OOV_TOKEN = "_"
N_LETTERS = len(ALLOWED_CHARACTERS)
CHAR_TO_INDEX = {char: idx for idx, char in enumerate(ALLOWED_CHARACTERS)}


@dataclass(frozen=True)
class NameRecord:
    name: str
    raw_name: str
    label: str
    label_id: int
    length: int


def set_seed(seed: int, use_cuda: bool = False) -> None:
    """Fix the random sources used by Python, NumPy and PyTorch."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if use_cuda:
        torch.cuda.manual_seed_all(seed)
    if torch.backends.cudnn.is_available():
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def unicode_to_ascii(text: str) -> str:
    """Convert a Unicode name to the ASCII alphabet used by the tutorial."""
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn" and char in ALLOWED_CHARACTERS
    )


def letter_to_index(letter: str) -> int:
    return CHAR_TO_INDEX.get(letter, CHAR_TO_INDEX[OOV_TOKEN])


def line_to_tensor(line: str) -> torch.Tensor:
    """Return a tensor with shape [sequence_length, n_letters]."""
    tensor = torch.zeros(len(line), N_LETTERS, dtype=torch.float32)
    for pos, letter in enumerate(line):
        tensor[pos, letter_to_index(letter)] = 1.0
    return tensor


def check_data_dir(data_dir: Path) -> None:
    txt_files = sorted(data_dir.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(
            f"No *.txt files were found in {data_dir}.\n"
            "Put the tutorial data under data/names, or run: python scripts/download_data.py"
        )


def load_name_records(data_dir: Path) -> tuple[list[NameRecord], list[str]]:
    """Load all names. Each text file name is used as one language label."""
    check_data_dir(data_dir)
    labels = sorted(path.stem for path in data_dir.glob("*.txt"))
    label_to_id = {label: idx for idx, label in enumerate(labels)}

    records: list[NameRecord] = []
    for file_path in sorted(data_dir.glob("*.txt")):
        label = file_path.stem
        with file_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                raw_name = raw_line.strip()
                name = unicode_to_ascii(raw_name)
                if not name:
                    continue
                records.append(
                    NameRecord(
                        name=name,
                        raw_name=raw_name,
                        label=label,
                        label_id=label_to_id[label],
                        length=len(name),
                    )
                )
    if not records:
        raise ValueError(f"The files in {data_dir} did not contain usable names.")
    return records, labels


def stratified_split(
    records: list[NameRecord],
    val_ratio: float,
    seed: int,
) -> tuple[list[NameRecord], list[NameRecord]]:
    """Split records by class, so each language appears in both sets."""
    rng = random.Random(seed)
    by_label: dict[int, list[NameRecord]] = {}
    for record in records:
        by_label.setdefault(record.label_id, []).append(record)

    train_records: list[NameRecord] = []
    val_records: list[NameRecord] = []
    for label_id in sorted(by_label):
        items = by_label[label_id][:]
        rng.shuffle(items)
        n_val = max(1, int(round(len(items) * val_ratio)))
        n_val = min(n_val, len(items) - 1) if len(items) > 1 else 1
        val_records.extend(items[:n_val])
        train_records.extend(items[n_val:])

    rng.shuffle(train_records)
    rng.shuffle(val_records)
    return train_records, val_records


class NameDataset(Dataset):
    """Small in-memory dataset for character-level name classification."""

    def __init__(self, records: Iterable[NameRecord]):
        self.records = list(records)
        self.tensors = [line_to_tensor(record.name) for record in self.records]

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int):
        record = self.records[index]
        return {
            "x": self.tensors[index],
            "y": torch.tensor(record.label_id, dtype=torch.long),
            "length": record.length,
            "name": record.name,
            "raw_name": record.raw_name,
            "label": record.label,
        }


def collate_names(batch: list[dict]) -> dict:
    """Pad variable-length names to [max_len, batch, n_letters]."""
    lengths = torch.tensor([item["length"] for item in batch], dtype=torch.long)
    max_len = int(lengths.max().item())
    batch_size = len(batch)
    x = torch.zeros(max_len, batch_size, N_LETTERS, dtype=torch.float32)
    y = torch.empty(batch_size, dtype=torch.long)

    names: list[str] = []
    raw_names: list[str] = []
    labels: list[str] = []
    for batch_idx, item in enumerate(batch):
        seq_len = item["x"].shape[0]
        x[:seq_len, batch_idx, :] = item["x"]
        y[batch_idx] = item["y"]
        names.append(item["name"])
        raw_names.append(item["raw_name"])
        labels.append(item["label"])

    return {
        "x": x,
        "y": y,
        "lengths": lengths,
        "names": names,
        "raw_names": raw_names,
        "labels": labels,
    }


def dataset_summary(records: list[NameRecord], labels: list[str]) -> dict:
    lengths = [record.length for record in records]
    counts = {label: 0 for label in labels}
    for record in records:
        counts[record.label] += 1
    return {
        "n_samples": len(records),
        "n_classes": len(labels),
        "n_letters": N_LETTERS,
        "min_length": min(lengths),
        "mean_length": float(np.mean(lengths)),
        "max_length": max(lengths),
        "class_counts": counts,
    }


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def save_class_distribution(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["label", "count"])
        for label, count in summary["class_counts"].items():
            writer.writerow([label, count])
