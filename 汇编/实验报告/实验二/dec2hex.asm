.386
.model flat, stdcall
option casemap:none

include \masm32\include\windows.inc
include \masm32\include\kernel32.inc
include \masm32\include\masm32.inc
includelib \masm32\lib\kernel32.lib
includelib \masm32\lib\masm32.lib

.data
dstr    BYTE 20 DUP(0)
strin   BYTE "Please input a decimal number(0~4294967295):",0
strout  BYTE "The hexadecimal number is:",0
decnum  DWORD 0
const10 DWORD 10
hstr    BYTE 9 DUP(0)                 ; 8 位十六进制 + 终止 0

.code
start:
    ; 读入十进制 ASCII
    invoke  StdOut, addr strin
    invoke  StdIn,  addr dstr, 20
    ;字符串 → 十进制 DWORD（×10 累加）
    xor     esi, esi                 ; i = 0

L1:
    xor     ebx, ebx                 ; 每轮先把 EBX 清零
    mov     bl, [dstr+esi]           ; 取当前字符
    cmp     bl, 0
    je      to_hex                   ; 结束
    sub     bl, 48                   ; 只对 BL 做减法：'0'..'9' → 0..9
    mov     eax, decnum
    xor     edx, edx                 ; mul 前 EDX 必须为 0（无符号）
    mul     const10                  ; EDX:EAX = EAX * 10
    add     eax, ebx                 ; + 当前数字
    mov     decnum, eax
    inc     esi
    jmp     L1

to_hex:
    ; 十进制 DWORD → 8 位十六进制字符串（除 16 取余）
    mov     eax, decnum
    mov     ebx, 16
    mov     ecx, 8
    lea     esi, hstr+7              ; 从末位往前写 8 个字符
L2:
    xor     edx, edx                 ; div 前清 EDX
    div     ebx                      ; EAX=商, EDX=余(0..15)
    add     dl, 48                   ; 先映射到 '0'..'9'
    cmp     dl, 57                   ; '9'
    jbe     L3
    add     dl, 7                    ; 10..15 → 'A'..'F'（= 48+7 = 55 的效果）
L3:
    mov     [esi], dl                ; 写一位字符
    dec     esi
    loop    L2
    ; 加 0 终止（固定 8 位）
    mov     BYTE PTR [hstr+8], 0
    invoke  StdOut, addr strout
    invoke  StdOut, addr hstr
    invoke  ExitProcess, 0
END start
