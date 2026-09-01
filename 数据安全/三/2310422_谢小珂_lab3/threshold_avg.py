import secrets
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from itertools import combinations
from typing import List, Tuple, Dict

# ==========================================
# 密码学参数配置 (Cryptographic Parameters)
# ==========================================
P = 1_000_000_007  # 有限域 GF(P) 的安全大素数
T = 2              # 门限值 (Threshold)：任意 2 个计算节点即可恢复
N = 3              # 参与方总数 (Total Parties)
X_COORDS = [1, 2, 3]  # 三个计算方公开持有的非零横坐标

class CryptoEngine:
    """提供有限域 GF(P) 上的核心数学运算与追溯"""
    
    @staticmethod
    def mod_inverse(a: int, p: int) -> int:
        """费马小定理计算模逆元: a^(p-2) ≡ a^-1 (mod p)"""
        a %= p
        if a == 0:
            raise ZeroDivisionError("0 在有限域中没有乘法逆元。")
        return pow(a, p - 2, p)

    @staticmethod
    def eval_poly(coeffs: List[int], x: int, p: int) -> int:
        """霍纳法则计算多项式 f(x) (mod p)"""
        result = 0
        power = 1
        for coeff in coeffs:
            result = (result + coeff * power) % p
            power = (power * x) % p
        return result

    @staticmethod
    def verbose_lagrange(points: List[Tuple[int, int]], p: int) -> Tuple[int, Dict[int, int]]:
        """带有过程追溯的拉格朗日插值（计算 f(0)）"""
        secret = 0
        basis_coefficients = {}
        for i, (x_i, y_i) in enumerate(points):
            numerator, denominator = 1, 1
            for j, (x_j, _) in enumerate(points):
                if i == j:
                    continue
                numerator = (numerator * (-x_j)) % p
                denominator = (denominator * (x_i - x_j)) % p
            
            inv_den = CryptoEngine.mod_inverse(denominator, p)
            basis = (numerator * inv_den) % p
            basis_coefficients[x_i] = basis
            secret = (secret + y_i * basis) % p
        return secret, basis_coefficients

class DataOwner:
    """数据拥有者：负责输入、放大、多项式盲化、份额分发"""
    def __init__(self, owner_id: int, raw_value: str, scale: int):
        self.owner_id = owner_id
        self.raw_value = raw_value
        
        # 处理负数和小数的有限域映射
        self.scaled_int = int(Decimal(raw_value) * scale)
        self.secret_in_field = self.scaled_int % P  # 负数在此处会自动转换为域内的正整数
        
        # 使用 secrets 模块生成真随机系数
        self.random_coeff = secrets.randbelow(P - 1) + 1 
        self.coeffs = [self.secret_in_field, self.random_coeff]

    def print_polynomial_info(self):
        print(f"  [+] Data Owner {self.owner_id}:")
        print(f"      - 原始输入: {self.raw_value} -> 放大整数: {self.scaled_int} -> 有限域映射: {self.secret_in_field}")
        print(f"      - 盲化随机系数 (斜率 a1): {self.random_coeff}")
        print(f"      - 安全多项式: f_{self.owner_id}(x) = {self.secret_in_field} + {self.random_coeff} * x (mod P)")

    def generate_shares(self) -> Dict[int, int]:
        shares = {}
        for x in X_COORDS:
            shares[x] = CryptoEngine.eval_poly(self.coeffs, x, P)
        return shares

class ComputeNode:
    """计算节点：只负责同态聚合，对原始数据和总和完全无感知"""
    def __init__(self, node_id: int, x_coord: int):
        self.node_id = node_id
        self.x_coord = x_coord
        self.received_shares: Dict[int, int] = {} 

    def receive_share(self, owner_id: int, share_y: int):
        self.received_shares[owner_id] = share_y

    def print_stored_shares(self):
        shares_str = ", ".join([f"来自 Owner {oid} = {y}" for oid, y in self.received_shares.items()])
        print(f"  [>] Compute Node {self.node_id} (x={self.x_coord}) 密文缓冲区: [{shares_str}]")

    def compute_local_sum(self) -> Tuple[int, int]:
        local_sum = sum(self.received_shares.values()) % P
        return (self.x_coord, local_sum)

def get_user_inputs() -> List[str]:
    """支持复杂输入的交互函数"""
    print("交互输入阶段: 请依次输入三方的秘密数据（支持正负数、小数）:")
    default_values = ["85.5", "-12.25", "100"]
    inputs = []
    for i in range(1, 4):
        user_in = input(f"    Data Owner {i} 的数据: ").strip()
        if not user_in:
            inputs.append(default_values[i-1])
        else:
            try:
                Decimal(user_in)
                inputs.append(user_in)
            except InvalidOperation:
                print(f"    输入非法，自动回退为默认值: {default_values[i-1]}")
                inputs.append(default_values[i-1])
    return inputs

def main():
    # 步骤 1：数据输入与自适应动态放大
    raw_inputs = get_user_inputs()
    decimals = [Decimal(val) for val in raw_inputs]
    
    # 动态确定最大小数位以精确防止精度丢失
    max_places = max(abs(d.as_tuple().exponent) for d in decimals)
    scale = 10 ** max_places
    
    print(f"\n【1. 数据预处理与编码】")
    print(f"  最大小数位数为 {max_places} 位，自适应放大倍数: {scale}")

    # 步骤 2：初始化实体与多项式构造
    print(f"\n【2. 本地盲化与安全多项式构造】")
    owners = [DataOwner(i+1, val, scale) for i, val in enumerate(raw_inputs)]
    for owner in owners:
        owner.print_polynomial_info()

    # 步骤 3：跨网络份额分发
    print(f"\n【3. 秘密份额跨网络分发】")
    compute_nodes = [ComputeNode(i+1, x) for i, x in enumerate(X_COORDS)]
    
    for owner in owners:
        shares = owner.generate_shares()
        print(f"  [*] Owner {owner.owner_id} 开始分发：")
        for node in compute_nodes:
            y_share = shares[node.x_coord]
            node.receive_share(owner.owner_id, y_share)
            print(f"      -> 节点 {node.node_id} (x={node.x_coord}) 接收子份额 y = {y_share}")

    # 步骤 4：隔离区状态审计
    print(f"\n【4. 计算节点密文审计】")
    for node in compute_nodes:
        node.print_stored_shares()

    # 步骤 5：同态本地求和
    print(f"\n【5. 节点本地执行同态求和】")
    local_sum_shares = []
    for node in compute_nodes:
        coord, local_sum = node.compute_local_sum()
        local_sum_shares.append((coord, local_sum))
        print(f"  [∑] Compute Node {node.node_id} 聚合密文点: (x = {coord}, d = {local_sum})")

    # 步骤 6：门限组合重构与数学推导追溯
    print(f"\n【6. 门限组合解密与拉格朗日公式重构追溯】")
    
    for combo in combinations(local_sum_shares, T):
        node_ids = [X_COORDS.index(p[0]) + 1 for p in combo]
        combo_name = f"{{Compute Node {node_ids[0]}, Compute Node {node_ids[1]}}}"
        print(f"  [>] 尝试使用节点组合: {combo_name}")
        
        sum_field, basis_map = CryptoEngine.verbose_lagrange(list(combo), P)
        
        print(f"      - 数学推导中间件:")
        for x_coord, delta in basis_map.items():
            print(f"        * 节点(x={x_coord}) 的拉格朗日插值基函数系数 Δ_{x_coord}(0) = {delta}")
            
        print(f"      - 有限域内重构总和结果 F(0) = {sum_field}")

        # 步骤 7：有限域负数解码、去放大与求均值
        # 处理有限域内的带符号整数回绕（大素数的一半作为正负分界线）
        decoded_sum = sum_field
        if sum_field > P // 2:
            decoded_sum -= P
            print(f"      - [检测到模回绕] 该有限域正数代表负数 -> 映射回复数真实值: {decoded_sum}")
        else:
            print(f"      - [未检测到模回绕] 映射回正数真实值: {decoded_sum}")

        # 计算最终真实值
        true_sum = Fraction(decoded_sum, scale)
        true_avg = Fraction(true_sum, N)
        
        print(f"      - 除去缩放因子 -> 真实三方数据总和 = {float(true_sum)}")
        print(f"      - 重构最终平均值 (总和 / {N}) = {float(true_avg):.4f}")
        print("-" * 65)

    # 明文对比基准
    plaintext_sum = sum(decimals)
    plaintext_avg = plaintext_sum / N
    print(f"\n【7. 权威明文基准对照验证】")
    print(f"  [√] 明文直接累计总和: {plaintext_sum}")
    print(f"  [√] 明文直接计算均值: {plaintext_avg:.4f}\n")

if __name__ == "__main__":
    main()