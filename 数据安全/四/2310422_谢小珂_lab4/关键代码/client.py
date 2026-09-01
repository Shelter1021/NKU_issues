#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import base64
import csv
import random
from collections import Counter
from pathlib import Path
from typing import Any

import pymysql
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

# Demo key/iv are fixed only to make one run easy to debug.
# Frequency hiding still comes from a fresh random IV in every encryption.
KEY = b"Nankai-FHOPE-Key"
BASE_IV = b"Nankai-FHOPE-IV!"

ORIGINAL_VALUES = ["apple", "pear", "banana", "orange", "cherry", "apple", "cherry", "orange"]
SKEWED_BASE = [5, 5, 5, 5, 5, 3, 3, 7, 7, 9, 1, 2, 5, 5, 6, 6, 8, 5, 4, 5]

local_table: dict[Any, int] = {}


def aes_enc(plaintext: bytes, iv: bytes) -> bytes:
    aes = AES.new(KEY, AES.MODE_CBC, iv=iv)
    return aes.encrypt(pad(plaintext, AES.block_size, style="pkcs7"))


def aes_dec(ciphertext: bytes, iv: bytes) -> bytes:
    aes = AES.new(KEY, AES.MODE_CBC, iv=iv)
    return unpad(aes.decrypt(ciphertext), AES.block_size, style="pkcs7")


def plaintext_text(value: Any) -> str:
    return str(value)


def random_encrypt(plaintext: Any) -> str:
    raw = plaintext_text(plaintext).encode("utf-8")
    iv = get_random_bytes(16)
    inner = aes_enc(raw, iv)
    outer = aes_enc(iv + inner, BASE_IV)
    return base64.b64encode(outer).decode("utf-8")


def random_decrypt(ciphertext: str) -> str:
    outer = base64.b64decode(ciphertext.encode("utf-8"))
    plaintext = aes_dec(outer, BASE_IV)
    inner_iv = plaintext[:16]
    inner_ct = plaintext[16:]
    return aes_dec(inner_ct, inner_iv).decode("utf-8")


def sorted_table_snapshot() -> dict[Any, int]:
    return dict(sorted(local_table.items(), key=lambda kv: kv[0]))


def cal_pos(plaintext: Any) -> tuple[int, dict[Any, int], dict[Any, int]]:
    before = sorted_table_snapshot()
    presum = sum(v for k, v in local_table.items() if k < plaintext)

    if plaintext in local_table:
        local_table[plaintext] += 1
        count = local_table[plaintext]
        pos = random.randint(presum, presum + count - 1)
    else:
        local_table[plaintext] = 1
        pos = presum

    after = sorted_table_snapshot()
    return pos, before, after


def get_left_pos(plaintext: Any) -> int:
    return sum(v for k, v in local_table.items() if k < plaintext)


def get_right_pos(plaintext: Any) -> int:
    return sum(v for k, v in local_table.items() if k <= plaintext)


class RunLogger:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = (self.run_dir / "run.log").open("w", encoding="utf-8")

    def info(self, msg: str) -> None:
        print(msg)
        self.log_file.write(msg + "\n")
        self.log_file.flush()

    def close(self) -> None:
        self.log_file.close()


def connect(args: argparse.Namespace):
    return pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        autocommit=False,
    )


def table_snapshot(cur) -> dict[str, int]:
    cur.execute("SELECT ciphertext, encoding FROM example")
    return {row[0]: int(row[1]) for row in cur.fetchall()}


def split_stats(cur) -> tuple[int, int]:
    cur.execute("SELECT FHLeafSplits(), FHInternalSplits()")
    row = cur.fetchone()
    return int(row[0]), int(row[1])


def reset_table(args: argparse.Namespace, logger: RunLogger) -> None:
    global local_table
    local_table = {}
    with connect(args) as db:
        with db.cursor() as cur:
            cur.execute("CALL pro_reset()")
            db.commit()
    logger.info("[reset] local_table cleared, MySQL table truncated, FH-OPE tree reset")


def insert_one(args: argparse.Namespace, plaintext: Any, insert_index: int,
               workload: str, logger: RunLogger) -> dict[str, Any]:
    pos, before_local, after_local = cal_pos(plaintext)
    ciphertext = random_encrypt(plaintext)

    with connect(args) as db:
        with db.cursor() as cur:
            before_db = table_snapshot(cur)
            before_leaf, before_internal = split_stats(cur)

            cur.execute("CALL pro_insert(%s, %s)", (pos, ciphertext))
            db.commit()

            cur.execute("SELECT FHStart(), FHEnd()")
            fh_start, fh_end = cur.fetchone()
            after_db = table_snapshot(cur)
            after_leaf, after_internal = split_stats(cur)

    changed = [
        (ct, old_code, after_db[ct])
        for ct, old_code in before_db.items()
        if ct in after_db and int(after_db[ct]) != int(old_code)
    ]

    leaf_delta = after_leaf - before_leaf
    internal_delta = after_internal - before_internal
    update_triggered = bool(changed or int(fh_start) != -1)
    inserted_encoding = int(after_db.get(ciphertext, 0))

    row = {
        "workload": workload,
        "insert_index": insert_index,
        "plaintext": plaintext_text(plaintext),
        "pos": pos,
        "encoding": inserted_encoding,
        "ciphertext_prefix": ciphertext[:32],
        "ciphertext": ciphertext,
        "local_table_before": repr(before_local),
        "local_table_after": repr(after_local),
        "leaf_splits_before": before_leaf,
        "leaf_splits_after": after_leaf,
        "leaf_split_delta": leaf_delta,
        "internal_splits_before": before_internal,
        "internal_splits_after": after_internal,
        "internal_split_delta": internal_delta,
        "update_triggered": int(update_triggered),
        "fh_start": int(fh_start),
        "fh_end": int(fh_end),
        "changed_rows": len(changed),
        "changed_preview": ";".join(f"{old}->{new}" for _, old, new in changed[:6]),
    }

    logger.info(
        f"[{workload}] insert #{insert_index:02d} plaintext={plaintext_text(plaintext)!r} "
        f"pos={pos} encoding={inserted_encoding} "
        f"leaf={before_leaf}->{after_leaf} internal={before_internal}->{after_internal} "
        f"update={'YES' if update_triggered else 'NO'} changed_rows={len(changed)}"
    )
    if update_triggered:
        logger.info(
            f"  [event] encoding_update FHStart={fh_start} FHEnd={fh_end} "
            f"changed={row['changed_preview']}"
        )

    return row


def search_range(args: argparse.Namespace, left: Any, right: Any,
                 logger: RunLogger) -> tuple[list[str], dict[str, Any]]:
    left_pos = get_left_pos(left)
    right_pos = get_right_pos(right)
    total = sum(local_table.values())

    with connect(args) as db:
        with db.cursor() as cur:
            cur.execute("SELECT FHSearch(%s)", (left_pos,))
            left_code = int(cur.fetchone()[0])

            if right_pos >= total:
                right_code = (1 << 63) - 1
            else:
                cur.execute("SELECT FHSearch(%s)", (right_pos,))
                right_code = int(cur.fetchone()[0])

            cur.execute(
                """
                SELECT id, encoding, ciphertext
                FROM example
                WHERE encoding >= %s AND encoding < %s
                ORDER BY encoding, id
                """,
                (left_code, right_code),
            )
            rows = cur.fetchall()

    plaintexts = [random_decrypt(row[2]) for row in rows]
    logger.info(
        f"[query] plaintext_range=[{left},{right}] pos_range=[{left_pos},{right_pos}) "
        f"code_range=[{left_code},{right_code}) returned={len(rows)}"
    )
    for db_id, encoding, ciphertext in rows[:30]:
        logger.info(
            f"  id={db_id:<3} encoding={encoding:<8} "
            f"cipher_prefix={ciphertext[:24]} plaintext={random_decrypt(ciphertext)}"
        )
    if len(rows) > 30:
        logger.info(f"  ... {len(rows) - 30} more rows omitted in console")

    meta = {
        "query_left": plaintext_text(left),
        "query_right": plaintext_text(right),
        "left_pos": left_pos,
        "right_pos": right_pos,
        "left_code": left_code,
        "right_code": right_code,
        "returned_count": len(rows),
    }
    return plaintexts, meta


def generate_values(args: argparse.Namespace) -> list[Any]:
    if args.mode == "original":
        return list(ORIGINAL_VALUES)
    if args.mode == "same-number":
        value = int(args.value) if args.value is not None else 5
        return [value] * args.count
    if args.mode == "same-string":
        value = args.value if args.value is not None else "apple"
        return [str(value)] * args.count
    if args.mode == "increasing":
        return list(range(1, args.count + 1))
    if args.mode == "skewed":
        values = list(SKEWED_BASE)
        while len(values) < args.count:
            values.extend(SKEWED_BASE)
        return values[:args.count]
    if args.mode == "random-small-domain":
        return [random.randint(1, args.domain_size) for _ in range(args.count)]
    raise ValueError(f"unknown mode: {args.mode}")


def query_bounds(args: argparse.Namespace, values: list[Any]) -> tuple[Any, Any]:
    if args.mode == "original":
        return "b", "p"
    if args.mode == "same-number":
        value = int(args.value) if args.value is not None else 5
        return value, value
    if args.mode == "same-string":
        value = args.value if args.value is not None else "apple"
        return str(value), str(value)
    if args.mode == "increasing":
        return max(1, args.count // 4), max(1, (args.count * 3) // 4)
    if args.mode in ("skewed", "random-small-domain"):
        return 3, 7
    mn, mx = min(values), max(values)
    return mn, mx


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> None:
    random.seed(args.seed)
    values = generate_values(args)
    run_name = args.run_name or f"{args.mode}_{len(values)}"
    run_dir = Path(args.results_dir) / run_name
    logger = RunLogger(run_dir)

    try:
        logger.info(f"[config] run_name={run_name} mode={args.mode} count={len(values)} seed={args.seed}")
        logger.info(f"[config] values={values}")

        if args.reset:
            reset_table(args, logger)

        insert_rows: list[dict[str, Any]] = []
        for i, plaintext in enumerate(values, start=1):
            insert_rows.append(insert_one(args, plaintext, i, args.mode, logger))

        write_csv(run_dir / "insert_details.csv", insert_rows)

        left, right = query_bounds(args, values)
        actual_plaintexts, query_meta = search_range(args, left, right, logger)
        expected_plaintexts = [plaintext_text(v) for v in values if left <= v <= right]
        query_correct = Counter(expected_plaintexts) == Counter(actual_plaintexts)

        query_rows = [{
            "workload": args.mode,
            **query_meta,
            "expected_count": len(expected_plaintexts),
            "actual_count": len(actual_plaintexts),
            "query_correct": int(query_correct),
            "expected_counter": repr(dict(Counter(expected_plaintexts))),
            "actual_counter": repr(dict(Counter(actual_plaintexts))),
        }]
        write_csv(run_dir / "query_results.csv", query_rows)

        unique_plaintexts = len(set(plaintext_text(v) for v in values))
        unique_ciphertexts = len(set(r["ciphertext"] for r in insert_rows))
        unique_encodings = len(set(r["encoding"] for r in insert_rows))
        summary = [{
            "run_name": run_name,
            "workload": args.mode,
            "count": len(values),
            "unique_plaintexts": unique_plaintexts,
            "unique_ciphertexts": unique_ciphertexts,
            "unique_inserted_encodings": unique_encodings,
            "leaf_splits": insert_rows[-1]["leaf_splits_after"] if insert_rows else 0,
            "internal_splits": insert_rows[-1]["internal_splits_after"] if insert_rows else 0,
            "encoding_updates": sum(int(r["update_triggered"]) for r in insert_rows),
            "changed_rows_total": sum(int(r["changed_rows"]) for r in insert_rows),
            "query_correct": int(query_correct),
        }]
        write_csv(run_dir / "workload_summary.csv", summary)

        logger.info(
            f"[query-check] expected={len(expected_plaintexts)} actual={len(actual_plaintexts)} "
            f"correct={'YES' if query_correct else 'NO'}"
        )
        logger.info(
            f"[summary] unique_plaintexts={unique_plaintexts} unique_ciphertexts={unique_ciphertexts} "
            f"unique_inserted_encodings={unique_encodings} leaf_splits={summary[0]['leaf_splits']} "
            f"internal_splits={summary[0]['internal_splits']} updates={summary[0]['encoding_updates']}"
        )
        logger.info(f"[files] saved to {run_dir}")
    finally:
        logger.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="FH-OPE client experiment runner")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--user", default="fhope")
    p.add_argument("--password", default="123456")
    p.add_argument("--database", default="fhope_lab")
    p.add_argument("--mode", default="same-number",
                   choices=["original", "same-number", "same-string", "increasing", "skewed", "random-small-domain"])
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--value", default=None)
    p.add_argument("--domain-size", type=int, default=10)
    p.add_argument("--seed", type=int, default=20260606)
    p.add_argument("--results-dir", default="results")
    p.add_argument("--run-name", default=None)
    p.add_argument("--reset", action="store_true", default=True)
    p.add_argument("--no-reset", dest="reset", action="store_false")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
