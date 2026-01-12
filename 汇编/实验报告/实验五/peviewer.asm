; 实验：PEViewer
; 功能：
;   输入一个 PE 文件名，调用 CreateFile / SetFilePointer / ReadFile / CloseHandle
;   从文件中读取：
;       IMAGE_DOS_HEADER:      e_magic, e_lfanew
;       IMAGE_NT_HEADERS:      Signature
;       IMAGE_FILE_HEADER:     NumberOfSections, TimeDateStamp, Characteristics
;       IMAGE_OPTIONAL_HEADER: AddressOfEntryPoint, ImageBase,
;                              SectionAlignment, FileAlignment
;   并以十六进制形式输出到命令行窗口。

.386
.model flat, stdcall
option casemap:none

; ==== MASM32 + Win32 控制台 ====
include \masm32\include\windows.inc
include \masm32\include\kernel32.inc
include \masm32\include\masm32.inc
include \masm32\macros\macros.asm

includelib \masm32\lib\kernel32.lib
includelib \masm32\lib\masm32.lib

.data

; --- 提示字符串 ---
promptInput      BYTE "Please input a PE file: ",0

; DOS 头
msgDosHeader     BYTE "IMAGE_DOS_HEADER",0Dh,0Ah,0
msgEMagic        BYTE "    e_magic: ",0
msgELfanew       BYTE "    e_lfanew: ",0

; NT 头
msgNtHeader      BYTE "IMAGE_NT_HEADERS",0Dh,0Ah,0
msgSignature     BYTE "    Signature: ",0

; 文件头
msgFileHeader    BYTE "IMAGE_FILE_HEADER",0Dh,0Ah,0
msgNumSections   BYTE "    NumberOfSections: ",0
msgTimeStamp     BYTE "    TimeDateStamp: ",0
msgChars         BYTE "    Characteristics: ",0

; 可选头
msgOptHeader     BYTE "IMAGE_OPTIONAL_HEADER",0Dh,0Ah,0
msgEntryPoint    BYTE "    AddressOfEntryPoint: ",0
msgImageBase     BYTE "    ImageBase: ",0
msgSecAlign      BYTE "    SectionAlignment: ",0
msgFileAlign     BYTE "    FileAlignment: ",0

endl             BYTE 0Dh,0Ah,0

; 输入的文件名
FileName         BYTE 260 DUP(0)          ; StdIn 读进来：例如 "bubble_sort.exe"

; 缓冲区
FileBuf          BYTE 4000 DUP(0)         ; 保存从文件中读出的前 4000 字节
HexBuf           BYTE 16   DUP(0)         ; 十六进制字符串缓冲区

; 变量
hFile            DWORD ?                  ; 文件句柄
BytesRead        DWORD ?                  ; 实际读取的字节数
BaseOffset       DWORD 0                  ; 当前结构基址（DOS 头=0，NT 头=e_lfanew）

.code

;-----------------------------------------------------
; dw2hex4
;   将 16 位数值转成 4 位十六进制 ASCII 字符串
;   value  : DWORD（只用低 16 位）
;   pBuf   : 指向至少 5 字节缓冲区，格式 "XXXX",0
;-----------------------------------------------------
dw2hex4 PROC USES eax ecx edx edi, value:DWORD, pBuf:PTR BYTE
    mov eax, value
    mov edi, pBuf
    mov ecx, 4
@@:
    mov edx, eax
    and edx, 0Fh
    cmp dl, 9
    jbe  short @digit
    add dl, 'A' - 10
    jmp  short @store
@digit:
    add dl, '0'
@store:
    mov [edi+ecx-1], dl
    shr eax, 4
    loop @B
    mov BYTE PTR [edi+4], 0
    ret
dw2hex4 ENDP

;-----------------------------------------------------
; OutputDword
;   读取 DWORD 并以 8 位十六进制输出
;   输入：
;       EDX = 字段相对于当前结构基址的偏移
;       BaseOffset = 当前结构基址（DOS:0 / NT:e_lfanew）
;-----------------------------------------------------
OutputDword PROC USES eax esi edx
    mov esi, OFFSET FileBuf
    add esi, BaseOffset       ; 结构基址（DOS 或 NT）
    add esi, edx              ; 再加字段偏移

    mov eax, DWORD PTR [esi]  ; 取出 4 字节字段值
    invoke dw2hex, eax, ADDR HexBuf      ; MASM32 自带：输出 8 个 hex
    invoke StdOut,  ADDR HexBuf
    invoke StdOut,  ADDR endl
    ret
OutputDword ENDP

;-----------------------------------------------------
; OutputWord
;   读取 WORD 并以 4 位十六进制输出（高位补 0）
;   输入：
;       EDX = 字段相对于当前结构基址的偏移
;-----------------------------------------------------
OutputWord PROC USES eax esi edx
    mov esi, OFFSET FileBuf
    add esi, BaseOffset
    add esi, edx

    movzx eax, WORD PTR [esi]           ; 只取 2 字节
    invoke dw2hex4, eax, ADDR HexBuf    ; 生成 4 位 hex 字符串
    invoke StdOut,  ADDR HexBuf
    invoke StdOut,  ADDR endl
    ret
OutputWord ENDP

;-----------------------------------------------------
; 程序入口
;-----------------------------------------------------
start:

    ; ========== 1. 输入文件名 ==========
    invoke StdOut, ADDR promptInput      ; 提示
    invoke StdIn,  ADDR FileName, 260    ; 读入文件名（以 0 结尾的字符串）

    ; ========== 2. 打开并读取文件 ==========
    invoke CreateFile, ADDR FileName, \
                       GENERIC_READ, \
                       FILE_SHARE_READ, \
                       NULL, \
                       OPEN_EXISTING, \
                       FILE_ATTRIBUTE_ARCHIVE, \
                       NULL
    mov  hFile, eax

    invoke SetFilePointer, hFile, 0, NULL, FILE_BEGIN
    invoke ReadFile, hFile, ADDR FileBuf, 4000, ADDR BytesRead, NULL

    ; ========== 3. IMAGE_DOS_HEADER ==========
    mov  BaseOffset, 0                    ; DOS 头基址 = 文件开头
    invoke StdOut, ADDR msgDosHeader

    ; e_magic（WORD，偏移 0） -> 5A4D
    invoke StdOut, ADDR msgEMagic
    mov  edx, 0
    invoke OutputWord

    ; e_lfanew（DWORD，偏移 3Ch）
    invoke StdOut, ADDR msgELfanew
    mov  edx, 3Ch
    invoke OutputDword

    ; 用 e_lfanew 的值更新 BaseOffset（NT 头基址）
    mov  esi, OFFSET FileBuf
    add  esi, 3Ch
    mov  eax, DWORD PTR [esi]            ; eax = e_lfanew
    mov  BaseOffset, eax                 ; BaseOffset = IMAGE_NT_HEADERS 相对文件开头的偏移

    ; ========== 4. IMAGE_NT_HEADERS ==========
    invoke StdOut, ADDR msgNtHeader

    ; Signature（DWORD，相对 NT 头偏移 0） -> 00004550
    invoke StdOut, ADDR msgSignature
    mov  edx, 0
    invoke OutputDword

    ; ========== 5. IMAGE_FILE_HEADER ==========
    invoke StdOut, ADDR msgFileHeader

    ; NumberOfSections（WORD，相对 NT 头偏移 6） -> 0003
    invoke StdOut, ADDR msgNumSections
    mov  edx, 6
    invoke OutputWord

    ; TimeDateStamp（DWORD，相对 NT 头偏移 8）
    invoke StdOut, ADDR msgTimeStamp
    mov  edx, 8
    invoke OutputDword

    ; Characteristics（WORD，相对 NT 头偏移 16h） -> 010F
    invoke StdOut, ADDR msgChars
    mov  edx, 16h
    invoke OutputWord

    ; ========== 6. IMAGE_OPTIONAL_HEADER ==========
    ; OptionalHeader 起始 = NT 头 + 18h
    ; 按 PPT 要求输出：
    ;   AddressOfEntryPoint : 28h
    ;   ImageBase           : 34h
    ;   SectionAlignment    : 38h
    ;   FileAlignment       : 3Ch

    invoke StdOut, ADDR msgOptHeader

    ; AddressOfEntryPoint（DWORD）
    invoke StdOut, ADDR msgEntryPoint
    mov  edx, 28h
    invoke OutputDword

    ; ImageBase（DWORD）
    invoke StdOut, ADDR msgImageBase
    mov  edx, 34h
    invoke OutputDword

    ; SectionAlignment（DWORD）
    invoke StdOut, ADDR msgSecAlign
    mov  edx, 38h
    invoke OutputDword

    ; FileAlignment（DWORD）
    invoke StdOut, ADDR msgFileAlign
    mov  edx, 3Ch
    invoke OutputDword

    ; ========== 7. 收尾 ==========
    invoke CloseHandle, hFile
    invoke ExitProcess, 0

END start
