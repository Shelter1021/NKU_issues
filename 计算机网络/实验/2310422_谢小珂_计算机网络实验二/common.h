#ifndef COMMON_H
#define COMMON_H

#include <iostream>
#include <string>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <chrono>
#include <vector>
#include <map>
#include <algorithm>
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")

// [配置] 这里的端口必须对应 Router 程序的设置
#define SERVER_IP "127.0.0.1"
#define ROUTER_PORT 8000  // 发送端把数据发给路由器 (Router入口)
#define SERVER_PORT 7000  // 接收端监听的端口 (Router出口转发给它)

// [配置] 协议参数
#define MSS 1024            // 最大分段大小 (数据载荷)
#define MAX_BUFFER_SIZE 10240 // 接收窗口缓冲区大小 (字节)，调大一点以便测试流量控制
#define MAX_SACK_BLOCKS 4   // [实验要求(3)] SACK块的最大数量

// [实验要求(2): 差错检测] 协议头部设计
// 包含序列号、确认号、校验和、长度、标志位、接收窗口
// [实验要求(3): 确认重传] 新增 SACK 块支持
struct Header {
    unsigned int seq;       // 序列号 (Sequence Number)
    unsigned int ack;       // 确认号 (Acknowledgment Number)
    unsigned short checkSum;// 校验和 (Checksum)
    unsigned short length;  // 数据长度

    unsigned char flags;    // 标志位 (SYN, ACK, FIN)
    unsigned short recvWindow; // [实验要求(4): 流量控制] 接收窗口大小 (rwnd)

    // [实验要求(3)] 选择确认 (SACK) 字段
    unsigned char sackCount;           // 有效的 SACK 块数量 (0-4)
    unsigned int sackBlocks[MAX_SACK_BLOCKS][2]; // [Start, End] 存储乱序收到的块范围
};

// 标志位宏定义
#define FLAG_SYN 0x01 // 建立连接
#define FLAG_ACK 0x02 // 确认
#define FLAG_FIN 0x04 // 断开连接
#define FLAG_DATA 0x08 // 普通数据

// 数据包结构
struct Packet {
    Header header;
    char data[MSS];
};

// [实验要求(2): 差错检测] 校验和计算函数
// 算法：16位反码求和 (One's Complement Sum)
unsigned short calculateChecksum(Packet* pkt) {
    unsigned int sum = 0;// 定义一个32位的变量 sum 来累加，防止16位加法溢出
    unsigned short* buf = (unsigned short*)pkt;
    // 注意：sizeof(Header) 已经包含了新增的 SACK 字段，所以这里自动覆盖了新字段
    // 计算需要校验的总字节数：
    // sizeof(Header) 是头部大小，pkt->header.length 是数据载荷长度
    int len = sizeof(Header) + pkt->header.length;
    // ==========================================
    // 关键步骤：备份并清零
    // ==========================================
    // 校验和字段本身在 Header 里。我们在计算校验和时，必须假设该字段为 0。
    // 如果不置 0，每次计算的结果都会包含上一次的值，导致错误。
    unsigned short oldSum = pkt->header.checkSum;
    pkt->header.checkSum = 0;

    // ==========================================
    // 步骤1：16位累加
    // ==========================================
    // 只要剩余长度大于 1字节 (至少还有2字节)，就当作一个 short 加到 sum 中
    while (len > 1) {
        sum += *buf++;// 把当前 16位数值加到 sum，buf 指针后移
        len -= 2;// 剩余长度减 2
    }
    // ==========================================
    // 步骤2：处理奇数尾部
    // ==========================================
    // 如果长度是奇数，最后会剩下一个字节。
    // 我们把它当作一个 16位整数的低8位（或高8位，视大小端而定）加进去。
    if (len > 0) {
        // *(unsigned char*)buf 取出最后一个字节
        // 直接加到 sum 中
        sum += *(unsigned char*)buf;
    }

    // ==========================================
     // 步骤3：回卷 (Folding) 处理溢出
     // ==========================================
     // sum 是 32位的，校验和是 16位的。
     // 如果 sum 超过了 0xFFFF (16位最大值)，高位的进位需要“回卷”加到低位上。
     // 这是一个循环，直到高16位全为0为止。
    while (sum >> 16) {
        sum = (sum & 0xffff) + (sum >> 16);
    }
    // ==========================================
    // 步骤4：恢复现场并返回
    // ==========================================
    pkt->header.checkSum = oldSum; // 把之前备份的校验和填回去，不破坏数据包原貌
    return (unsigned short)(~sum); // 最后一步：取反 (One's Complement)
    // 这是标准算法要求，接收方验证时结果应为 0 (或者全1)
}

#endif