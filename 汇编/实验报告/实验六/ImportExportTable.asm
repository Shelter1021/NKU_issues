; ====================================================================
; 文件名: Lab6_Final.asm
; 描述: 读取PE文件的导入表和导出表 (严格遵循实验6要求)
; 环境: MASM32 SDK
; 作者: 2310422谢小珂
; ====================================================================

.386
.model flat, stdcall
option casemap :none

include \masm32\include\windows.inc
include \masm32\include\kernel32.inc
include \masm32\include\masm32.inc
include \masm32\include\user32.inc

includelib \masm32\lib\kernel32.lib
includelib \masm32\lib\masm32.lib
includelib \masm32\lib\user32.lib

.data
    ; 提示信息与格式控制，严格对齐截图
    strInput        BYTE "Please input a PE file: ", 0
    strErrOpen      BYTE "Error: Cannot open file or file too large.", 0Dh, 0Ah, 0
    strImportTitle  BYTE "Import table:", 0Dh, 0Ah, 0
    strExportTitle  BYTE 0Dh, 0Ah, "Export table:", 0Dh, 0Ah, 0
    
    ; 格式化字符串
    fmtDllName      BYTE "    %s", 0Dh, 0Ah, 0       ; DLL名缩进4空格
    fmtFuncName     BYTE "        %s", 0Dh, 0Ah, 0   ; 函数名缩进8空格
    fmtExpName      BYTE "    %s", 0Dh, 0Ah, 0       ; 导出函数缩进4空格
    
    ; 缓冲区
    szFileName      BYTE 260 dup(0)
    hMapFile        DWORD 0
    lpBaseAddress   DWORD 0
    hFile           DWORD 0
    dwFileSize      DWORD 0
    
    ; 临时变量
    pNtHeader       DWORD 0
    pOptHeader      DWORD 0
    pSecHeader      DWORD 0
    nSecCount       WORD 0
    
    importRVA       DWORD 0
    exportRVA       DWORD 0

.code

; ====================================================================
; 子程序: RVAtoRAW
; 功能: 将 RVA 转换为文件偏移 (RAW)
; 参数: dwRVA - 相对虚拟地址
; 返回: EAX - 文件偏移地址 (如果失败返回0)
; ====================================================================
RVAtoRAW PROC uses ebx ecx edx esi edi dwRVA:DWORD
    
    ; 获取 NT 头和节表位置
    mov esi, lpBaseAddress
    add esi, [esi+3Ch]          ; ESI = PE Header (PE signature)
    mov pNtHeader, esi
    
    movzx ecx, word ptr [esi+06h] ; ecx = NumberOfSections
    
    ; 定位到节表 (Section Table)
    ; SectionTable = OptionalHeader + SizeOfOptionalHeader
    ; OptionalHeader 始于 PE Header + 18h
    ; SizeOfOptionalHeader 位于 PE Header + 14h
    movzx edx, word ptr [esi+14h]
    lea ebx, [esi + 18h]        ; ebx = OptionalHeader start
    add ebx, edx                ; ebx = Section Table start
    
    mov esi, ebx                ; ESI 指向第一个 IMAGE_SECTION_HEADER

    ; 遍历所有节
CheckSection:
    cmp ecx, 0
    je NotFound
    
    ; 比较 RVA 是否在 [VirtualAddress, VirtualAddress + SizeOfRawData]
    mov eax, [esi + 0Ch]        ; VirtualAddress
    mov edx, [esi + 10h]        ; SizeOfRawData
    
    cmp dwRVA, eax
    jb NextSection              ; 如果 RVA < VirtualAddress，下一个
    
    add edx, eax                ; edx = VirtualAddress + SizeOfRawData
    cmp dwRVA, edx
    jae NextSection             ; 如果 RVA >= 结束地址，下一个
    
    ; 找到了：RAW = RVA - VirtualAddress + PointerToRawData
    sub dwRVA, eax
    mov eax, [esi + 14h]        ; PointerToRawData
    add eax, dwRVA
    ret

NextSection:
    add esi, 28h                ; IMAGE_SECTION_HEADER 大小为 40 字节
    dec ecx
    jmp CheckSection

NotFound:
    xor eax, eax
    ret
RVAtoRAW ENDP

; ====================================================================
; 主程序
; ====================================================================
main PROC
    LOCAL rwBytes:DWORD

    ; 1. 输入文件名
    invoke StdOut, addr strInput
    invoke StdIn, addr szFileName, sizeof szFileName
    
    ; 去除换行符 (StdIn 可能会读入 CR/LF)
    lea esi, szFileName
StripLoop:
    mov al, [esi]
    cmp al, 0Dh
    je StripDone
    cmp al, 0Ah
    je StripDone
    cmp al, 0
    je StripDone
    inc esi
    jmp StripLoop
StripDone:
    mov byte ptr [esi], 0

    ; 2. 打开并读取文件 (使用内存映射文件稍微简化，或者直接读入内存)
    ; 为了兼容原代码逻辑，我们直接用 ReadFile 读入整个缓冲区
    invoke CreateFile, addr szFileName, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL
    mov hFile, eax
    cmp eax, INVALID_HANDLE_VALUE
    je ErrorHandler

    invoke GetFileSize, hFile, NULL
    mov dwFileSize, eax
    
    ; 分配内存
    invoke GlobalAlloc, GPTR, dwFileSize
    mov lpBaseAddress, eax
    
    invoke ReadFile, hFile, lpBaseAddress, dwFileSize, addr rwBytes, NULL
    invoke CloseHandle, hFile

    ; 3. 解析 PE 头
    mov esi, lpBaseAddress
    cmp word ptr [esi], 5A4Dh   ; 检查 MZ 标志
    jnz ErrorHandler
    
    mov eax, [esi+3Ch]          ; e_lfanew
    add eax, esi                ; EAX = PE Header address
    cmp dword ptr [eax], 00004550h ; 检查 PE\0\0 标志
    jnz ErrorHandler
    
    ; 获取数据目录表的 RVA
    ; OptionalHeader (32位) 中，DataDirectory 偏移为 60h (96)
    ; Export Table 是第 0 项
    ; Import Table 是第 1 项
    
    ; PE Header + 18h (OptionalHeader) + 60h (DataDirectory offset) = PE Header + 78h
    lea ebx, [eax + 78h]
    
    mov ecx, [ebx]              ; DataDirectory[0].VirtualAddress (Export)
    mov exportRVA, ecx
    
    mov ecx, [ebx + 8]          ; DataDirectory[1].VirtualAddress (Import)
    mov importRVA, ecx

    ; ====================================================================
    ; 4. 处理导入表
    ; ====================================================================
    invoke StdOut, addr strImportTitle
    
    cmp importRVA, 0
    je ProcessExport

    invoke RVAtoRAW, importRVA
    cmp eax, 0
    je ProcessExport
    add eax, lpBaseAddress
    mov esi, eax                ; ESI 指向 IMAGE_IMPORT_DESCRIPTOR 数组

ImportLoop:
    ; 检查 OriginalFirstThunk 是否为 0 (结束标志)
    ; 注意：有些编译器可能会把 OriginalFirstThunk 置 0，只用 FirstThunk
    ; 但 Name 字段必须有效
    cmp dword ptr [esi + 12], 0 ; Name RVA
    je ProcessExport            ; 如果 Name 为 0，认为结束

    ; --- 打印 DLL 名称 ---
    mov eax, [esi + 12]         ; Name RVA
    invoke RVAtoRAW, eax
    add eax, lpBaseAddress
    
    invoke wsprintf, addr szFileName, addr fmtDllName, eax ; 复用 szFileName 做缓冲
    invoke StdOut, addr szFileName

    ; --- 处理 Thunks (函数名) ---
    ; 优先使用 OriginalFirstThunk (INT)，如果为0则使用 FirstThunk (IAT)
    mov ebx, [esi]              ; OriginalFirstThunk
    cmp ebx, 0
    jnz GotThunk
    mov ebx, [esi + 16]         ; FirstThunk
GotThunk:
    invoke RVAtoRAW, ebx
    cmp eax, 0
    je NextDll
    add eax, lpBaseAddress
    mov edi, eax                ; EDI 指向 IMAGE_THUNK_DATA 数组

ThunkLoop:
    mov ecx, [edi]              ; 读取 Thunk 数据
    cmp ecx, 0
    je NextDll                  ; 结束

    ; 检查最高位，判断是序号导入还是名称导入 
    test ecx, 80000000h
    jnz IsOrdinal

    ; 名称导入: ECX 是指向 IMAGE_IMPORT_BY_NAME 的 RVA
    invoke RVAtoRAW, ecx
    add eax, lpBaseAddress
    add eax, 2                  ; 跳过 Hint (2字节)
    
    invoke wsprintf, addr szFileName, addr fmtFuncName, eax
    invoke StdOut, addr szFileName
    jmp NextThunk

IsOrdinal:
    ; 实验不做序号导入的输出要求，直接跳过
    jmp NextThunk

NextThunk:
    add edi, 4
    jmp ThunkLoop

NextDll:
    add esi, 20                 ; 下一个描述符 (20字节)
    jmp ImportLoop

    ; ====================================================================
    ; 5. 处理导出表
    ; ====================================================================
ProcessExport:
    invoke StdOut, addr strExportTitle
    
    cmp exportRVA, 0
    je TheEnd

    invoke RVAtoRAW, exportRVA
    cmp eax, 0
    je TheEnd
    add eax, lpBaseAddress
    mov esi, eax                ; ESI 指向 IMAGE_EXPORT_DIRECTORY

    ; 获取 AddressOfNames
    mov ecx, [esi + 24]         ; NumberOfNames
    cmp ecx, 0
    je TheEnd
    
    mov edx, [esi + 32]         ; AddressOfNames RVA
    invoke RVAtoRAW, edx
    add eax, lpBaseAddress
    mov edi, eax                ; EDI 指向名称指针表

ExportLoop:
    push ecx                    ; 保存计数器

    mov eax, [edi]              ; 获取函数名 RVA
    invoke RVAtoRAW, eax
    add eax, lpBaseAddress      ; EAX 现在是函数名字符串地址
    
    invoke wsprintf, addr szFileName, addr fmtExpName, eax
    invoke StdOut, addr szFileName

    add edi, 4
    pop ecx
    dec ecx
    jnz ExportLoop

TheEnd:
    invoke GlobalFree, lpBaseAddress
    invoke ExitProcess, 0

ErrorHandler:
    invoke StdOut, addr strErrOpen
    invoke ExitProcess, 1

main ENDP
END main