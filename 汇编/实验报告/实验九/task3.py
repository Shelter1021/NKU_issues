# Task 3 Reverse Engineering Solver
# 实验内容：计算 Task 3 的正确输入字符串
# 逻辑来源：根据反编译伪代码分析，验证逻辑为 Input[i] ^ 0xA5 == Target[i]

def solve_task3():
    # 1. 从反汇编代码(var_68起始)提取的目标硬编码字节序列
    # 对应地址: 00402ba9 - 00402c0a
    target_bytes = [
        0xF1, 0xC9, 0xE1, 0xFF, 0xE7, 0x93, 0xF4, 0xEF, 0xD4, 0xE8,
        0xEF, 0xC0, 0xCE, 0xFC, 0xE2, 0xD1, 0xFD, 0xC0, 0xF1, 0xFC
    ]

    # 2. 核心异或密钥 (来源于代码中的常量 0xA5)
    xor_key = 0xA5

    print("[-] Analyzing Task 3 logic...")
    print(f"[-] Target Bytes Length: {len(target_bytes)}")
    print(f"[-] XOR Key: 0x{xor_key:X}")

    # 3. 执行逆向解密计算
    # 公式: 明文 = 密文 ^ 密钥
    flag_chars = []
    for b in target_bytes:
        decoded_char = chr(b ^ xor_key)
        flag_chars.append(decoded_char)

    # 4. 拼接并输出结果
    flag = "".join(flag_chars)
    print("-" * 30)
    print(f"[+] Calculated Flag: {flag}")
    print("-" * 30)

if __name__ == "__main__":
    solve_task3()