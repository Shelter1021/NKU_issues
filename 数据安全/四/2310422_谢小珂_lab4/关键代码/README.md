# FH-OPE 频率隐藏顺序保持加密实验

本项目用于完成“参照教材 6.3.3 FH-OPE 实现，修改 client.py 连续插入相同数值多次，观察编码树分裂和编码更新”的课程实验。

## 文件说明

- `src/Node.h`, `src/Node.cpp`：服务端编码树，包含叶节点分裂、内部节点分裂、编码更新统计。
- `src/UDF.cpp`：MySQL UDF 桥接函数，包括 FHInsert、FHSearch、FHUpdate、FHStart、FHEnd、FHReset、FHLeafSplits、FHInternalSplits。
- `load.sql`：创建数据库、UDF 函数、表和存储过程。
- `client.py`：Python 客户端，完成随机加密、本地 local_table、随机插入位置、范围查询和 CSV 日志。
- `scripts/build_udf.sh`：编译安装 UDF，可选 observation/textbook 参数。
- `scripts/run_experiments.sh`：批量运行 original、same-number、same-string、increasing、skewed、random-small-domain。
- `scripts/analyze_results.py`：汇总 CSV 并生成图表。

## 快速运行

```bash
sudo apt update
sudo apt install -y mysql-server default-libmysqlclient-dev build-essential python3-pip pkg-config
pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

sudo service mysql start
sudo mysql
```

在 MySQL root 中执行：

```sql
CREATE USER IF NOT EXISTS 'fhope'@'localhost' IDENTIFIED BY '123456';
CREATE USER IF NOT EXISTS 'fhope'@'127.0.0.1' IDENTIFIED BY '123456';
GRANT ALL PRIVILEGES ON *.* TO 'fhope'@'localhost';
GRANT ALL PRIVILEGES ON *.* TO 'fhope'@'127.0.0.1';
FLUSH PRIVILEGES;
```

回到项目目录：

```bash
bash scripts/build_udf.sh observation
mysql -ufhope -p123456 < load.sql
python3 client.py --mode same-number --count 20 --value 5 --run-name same_number_20
bash scripts/run_experiments.sh
```
