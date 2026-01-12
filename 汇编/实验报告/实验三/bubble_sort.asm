;------------------------------------------------------------
;  bubble_sort.asm  (fixed for MASM32 ml 6.14)
;------------------------------------------------------------
.386
.model flat, stdcall
option casemap:none

include \masm32\include\windows.inc
include \masm32\include\kernel32.inc
include \masm32\include\masm32.inc

includelib \masm32\lib\kernel32.lib
includelib \masm32\lib\masm32.lib

ExitProcess PROTO :DWORD

.data
prompt      db  "Enter 10 unsigned integers separated by space or comma:",13,10,0
inBuf       db  120 dup(0)
arr         dd  10 dup(0)
outBuf      db  12 dup(0)
spaceStr    db  " ",0
crlf        db  13,10,0
digitFlag   db  0
exitMsg     db  "Press Enter to exit...",13,10,0

.code
main PROC
    ; 提示并读入
    invoke  StdOut, addr prompt
    invoke  StdIn, addr inBuf, 120

    mov     esi, OFFSET inBuf
    xor     ebx, ebx                 ; 当前正在累积的数
    xor     edi, edi                 ; arr 下标 0..9
    mov     byte ptr digitFlag, 0

parse_loop:
    mov     al, [esi]
    cmp     al, 0
    je      store_last               ; 行结束
    cmp     al, 13
    je      store_last
    cmp     al, 10
    je      store_last

    ; 分隔符？
    cmp     al, ' '
    je      maybe_store
    cmp     al, ','
    je      maybe_store

    ; -------- 是数字 ----------
    sub     al, '0'
    movzx   edx, al
    mov     eax, ebx
    mov     ecx, eax
    shl     eax, 3
    shl     ecx, 1
    add     eax, ecx
    add     eax, edx
    mov     ebx, eax
    mov     byte ptr digitFlag, 1    ; 标记读到数字
    jmp     next_char

maybe_store:                         ; 遇到分隔符
    cmp     byte ptr digitFlag, 1
    jne     skip_store               ; 连续分隔符就别存0
    mov     [arr + edi*4], ebx       ; 真正存数
    inc     edi
    xor     ebx, ebx
    mov     byte ptr digitFlag, 0
    cmp     edi, 10
    jae     start_sort
skip_store:
    ; 不存就继续往下走
next_char:
    inc     esi
    jmp     parse_loop

store_last:                          ; 行尾，把最后一个数存进去（前提是刚才确实读过数字）
    cmp     byte ptr digitFlag, 1
    jne     start_sort
    mov     [arr + edi*4], ebx
    inc     edi

start_sort:
    ; 冒泡排序
    mov     ecx, 9
outer_loop:
    mov     esi, OFFSET arr
    mov     edx, ecx
inner_loop:
    mov     eax, [esi]
    cmp     eax, [esi+4]
    jbe     no_swap
    xchg    eax, [esi+4]
    mov     [esi], eax
no_swap:
    add     esi, 4
    dec     edx
    jnz     inner_loop
    dec     ecx
    jnz     outer_loop

    ; 输出
    mov     edi, 0
print_loop:
    cmp     edi, 10
    jae     done_print
    mov     eax, [arr + edi*4]
    invoke  dwtoa, eax, addr outBuf
    invoke  StdOut, addr outBuf
    cmp     edi, 9
    je      skip_space
    invoke  StdOut, addr spaceStr
skip_space:
    inc     edi
    jmp     print_loop

done_print:
    invoke  StdOut, addr crlf
    ; 防止闪退
    invoke  StdOut, addr exitMsg
    invoke  StdIn, addr inBuf, 120
    invoke  ExitProcess, 0
main ENDP
END main
