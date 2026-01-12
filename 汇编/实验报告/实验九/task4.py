# Task 4 Reverse Engineering Solver
# 实验内容：计算 Task 4 的正确输入字符串
# 逻辑来源：反编译代码显示为链式加密: Cipher[i] = (Prev_Cipher ^ Input[i]) ^ 0x34

def solve_task4():
    # 1. 从反汇编代码(var_6c起始)提取的目标硬编码密文
    # 对应地址: 004014e6
    target_bytes = [
        0xF2, 0xA7, 0xF4, 0xA9, 0xFE, 0x95, 0xD2, 0x92, 
        0xd4, 0x89, 0xd3, 0x80, 0xeb, 0xbc, 0xe0, 0xb5, 
        0xed, 0xb5, 0xe4, 0xbe, 0xed, 0xbc
    ]
    
    # 2. 初始化变量
    # ecx_1 的初始值 (0xAB)，充当第一个字符加密时的"前一个密文"
    current_prev_cipher = 0xAB
    
    # 固定的异或常量
    xor_constant = 0x34
    
    print("[-] Analyzing Task 4 logic...")
    print(f"[-] Target Bytes Length: {len(target_bytes)}")
    print(f"[-] Initial Key (IV): 0x{current_prev_cipher:X}")
    
    flag_chars = []
    
    # 3. 执行链式逆向解密
    # 正向公式: C[i] = C[i-1] ^ P[i] ^ 0x34
    # 逆向公式: P[i] = C[i] ^ C[i-1] ^ 0x34
    for cipher_byte in target_bytes:
        # 计算明文字符
        plain_val = cipher_byte ^ current_prev_cipher ^ xor_constant
        flag_chars.append(chr(plain_val))
        
        # 关键步骤：更新"前一个密文"为当前密文字节，供下一次循环使用
        current_prev_cipher = cipher_byte
        
    # 4. 拼接并输出结果
    flag = "".join(flag_chars)
    print("-" * 30)
    print(f"[+] Calculated Flag: {flag}")
    print("-" * 30)

if __name__ == "__main__":
    solve_task4()