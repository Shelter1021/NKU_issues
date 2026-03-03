#include "common.h"

SOCKET serverSocket;
SOCKADDR_IN serverAddr, senderAddr;
int senderAddrLen = sizeof(senderAddr);

// [实验要求(3): 确认重传] 接收缓冲区 (实现选择确认/乱序重排)
// 使用 map 自动排序，存储 Sequence -> Packet
std::map<unsigned int, Packet> recvBuffer;
unsigned int expectedSeq = 1; // 期望收到的下一个序列号

FILE* fp = nullptr;
const char* SAVE_FILENAME = "received_file.out";

// 发送 ACK (包含 SACK 信息和流量控制 rwnd)
void sendAck(unsigned int ackNum) {
    Packet ackPkt;
    memset(&ackPkt, 0, sizeof(ackPkt));
    ackPkt.header.flags = FLAG_ACK;
    ackPkt.header.ack = ackNum;

    // [实验要求(4): 流量控制] 动态计算接收窗口
    // 窗口大小 = 最大缓冲区 - 当前已缓冲的字节数
    // 注意：Packet结构较大，这里简化按 MSS 计算占用
    long long usedBytes = recvBuffer.size() * MSS;
    long long freeSpace = MAX_BUFFER_SIZE - usedBytes;
    if (freeSpace < 0) freeSpace = 0;

    // 将字节转换为 MSS 个数单位，方便Sender处理
    ackPkt.header.recvWindow = (unsigned short)(freeSpace / MSS);

    // [实验要求(3): 选择确认] 生成 SACK 块
    // 遍历 recvBuffer，找到不连续的块
    ackPkt.header.sackCount = 0;// 初始化 SACK 块数量
    if (!recvBuffer.empty()) {
        int blockIndex = 0;
        auto it = recvBuffer.begin();// 迭代器指向缓冲区第一个包
        // 记录当前块的 起始(start) 和 结束(end)
        unsigned int startSeq = it->first;
        unsigned int endSeq = it->first;
        unsigned int lastSeq = it->first;// 上一个遍历到的序号

        it++; // 移动到第二个元素
        // 遍历整个 map，寻找连续的“岛屿”
        while (it != recvBuffer.end() && blockIndex < MAX_SACK_BLOCKS) {
            if (it->first == lastSeq + 1) {
                // [连续]：如果当前序号 == 上一个序号 + 1，说明是连续的
                  // 扩展当前块的结束边界
                endSeq = it->first;
            }
            else {
                // [断开]：如果不连续，说明中间又有丢包（产生了新的洞）
                 // 1. 结算当前块，写入 header
                ackPkt.header.sackBlocks[blockIndex][0] = startSeq;
                ackPkt.header.sackBlocks[blockIndex][1] = endSeq;
                blockIndex++;

                // 2. 开启一个新的块
                if (blockIndex < MAX_SACK_BLOCKS) {
                    startSeq = it->first;
                    endSeq = it->first;
                }
            }
            lastSeq = it->first;// 更新游标
            it++;
        }

        // 记录最后一个块 (如果在循环结束前没填满)
        if (blockIndex < MAX_SACK_BLOCKS) {
            ackPkt.header.sackBlocks[blockIndex][0] = startSeq;
            ackPkt.header.sackBlocks[blockIndex][1] = endSeq;
            blockIndex++;
        }
        ackPkt.header.sackCount = blockIndex;// 记录总共有几个 SACK 块
    }

    // 计算校验和
    ackPkt.header.checkSum = calculateChecksum(&ackPkt);

    // 直接回复给来源
    sendto(serverSocket, (char*)&ackPkt, sizeof(ackPkt), 0, (SOCKADDR*)&senderAddr, senderAddrLen);
}

int main() {
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2, 2), &wsaData);

    serverSocket = socket(AF_INET, SOCK_DGRAM, 0);
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(SERVER_PORT); // 7000
    serverAddr.sin_addr.s_addr = htonl(INADDR_ANY);

    if (bind(serverSocket, (SOCKADDR*)&serverAddr, sizeof(serverAddr)) == SOCKET_ERROR) {
        printf("[Error] Bind failed on port %d.\n", SERVER_PORT);
        return -1;
    }

    printf("================================================\n");
    printf("Receiver Listening on port %d...\n", SERVER_PORT);
    printf("Data will be saved to: %s\n", SAVE_FILENAME);
    printf("================================================\n");

    while (true) {
        Packet pkt;
        int len = recvfrom(serverSocket, (char*)&pkt, sizeof(Packet), 0, (SOCKADDR*)&senderAddr, &senderAddrLen);

        if (len > 0) {
            // [实验要求(2): 差错检测] 校验和验证
            if (calculateChecksum(&pkt) != pkt.header.checkSum) {// [验证失败]
            // 如果不相等，说明数据包在传输中损坏了（比特翻转）。
                // 逻辑说明：
        // 1. pkt.header.checkSum 是发送方填写的原始校验和。
        // 2. calculateChecksum(&pkt) 会对当前收到的包重新算一遍。
        //    (注意：calculateChecksum 内部会先把 header.checkSum 暂时置 0 进行计算)
        // 3. 如果传输过程中没有比特错误，重新计算的结果应该等于 header.checkSum。
                printf("[Error] Checksum failed! Drop Seq=%u\n", pkt.header.seq);
                continue; // 关键动作：直接丢弃 (Drop)
            // 不发送 ACK，也不写入文件。让发送方超时重传。
            }

            //[实验要求(1): 连接管理]  --- 处理 SYN (建立连接) 握手---
            if (pkt.header.flags & FLAG_SYN) {
                printf("\n[Handshake] SYN Received. Resetting...\n");
                // [状态复位] 收到 SYN 意味着新的连接开始，清空之前的状态
                expectedSeq = 1;// 重置期望序列号
                recvBuffer.clear();// 清空接收缓冲区 (防止旧数据干扰)

                if (fp) fclose(fp);
                fopen_s(&fp, SAVE_FILENAME, "wb");// 准备写入新文件
                // ==========================================
                // 第二次握手动作：发送 SYN + ACK
                // ==========================================
                Packet synAck;
                memset(&synAck, 0, sizeof(synAck));
                synAck.header.flags = FLAG_SYN | FLAG_ACK;// [关键] 同时置位
                synAck.header.seq = 0;
                synAck.header.checkSum = calculateChecksum(&synAck);// 计算校验和
                // 发送回 Sender
                sendto(serverSocket, (char*)&synAck, sizeof(synAck), 0, (SOCKADDR*)&senderAddr, senderAddrLen);
                continue;// 本次循环处理完毕，继续监听
            }

            // --- 处理 FIN (关闭连接) ---
            if (pkt.header.flags & FLAG_FIN) {
                printf("[Teardown] FIN Received.\n");
                // ==========================================
               // 第二次挥手动作：发送 ACK
               // ==========================================
               // 先回复 Sender：我知道你想断开了
                Packet ackPkt; memset(&ackPkt, 0, sizeof(ackPkt));
                ackPkt.header.flags = FLAG_ACK; ackPkt.header.checkSum = calculateChecksum(&ackPkt);
                sendto(serverSocket, (char*)&ackPkt, sizeof(ackPkt), 0, (SOCKADDR*)&senderAddr, senderAddrLen);

                // ==========================================
              // 第三次挥手动作：发送 FIN
             // ==========================================
              // 再告诉 Sender：我也传输完了，可以断开
                Packet finPkt; memset(&finPkt, 0, sizeof(finPkt));
                finPkt.header.flags = FLAG_FIN; finPkt.header.checkSum = calculateChecksum(&finPkt);
                sendto(serverSocket, (char*)&finPkt, sizeof(finPkt), 0, (SOCKADDR*)&senderAddr, senderAddrLen);

                if (fp) { fclose(fp); fp = nullptr; printf("[System] File saved.\n"); }
                continue;
            }

            // --- 处理数据 ---
            if (pkt.header.length > 0 || (pkt.header.flags == 0)) {
                unsigned int seq = pkt.header.seq;

                // 情况1：收到期望的包 (In-Order) -> 直接写入文件
                if (seq == expectedSeq) {
                    if (fp) fwrite(pkt.data, 1, pkt.header.length, fp);
                    expectedSeq++;

                    // [实验要求(3): 确认重传] 检查缓冲区里是否还有连续的包 (乱序重组)
                    // ==========================================
    // [考点：乱序重组] 
    // ==========================================
    // 既然现在的洞补上了，检查缓冲区(recvBuffer)里是不是有后续的包可以连起来了？
    // recvBuffer 是 std::map，会自动按 seq 排序，这大大简化了逻辑
                    //实现了乱序缓存。我使用 C++ 的 std::map 来存储所有乱序到达的包。
                        //GBN 会直接丢弃乱序包，导致大量不必要的重传，而我的接收端会把它们存起来
                    while (recvBuffer.count(expectedSeq)) {
                        printf("[Log] Reassembling Buffered Seq=%u\n", expectedSeq);
                        // 从缓存取出数据写入文件
                        if (fp) fwrite(recvBuffer[expectedSeq].data, 1, recvBuffer[expectedSeq].header.length, fp);
                        // 从缓存删除，释放内存
                        recvBuffer.erase(expectedSeq);
                        // 期望继续 +1
                        expectedSeq++;
                    }
                    // 所有的连续包都处理完了，回复最新的 ACK
                    sendAck(expectedSeq);
                }
                // 情况2：收到乱序包 (Out-of-Order) -> [实验要求] 选择确认/缓存
                else if (seq > expectedSeq) {
                    printf("[Log] Out-of-Order: Recv %u, Expected %u. Buffered.\n", seq, expectedSeq);
                    recvBuffer[seq] = pkt;
                    // 不丢弃包！存入 map 中等待后续处理。
    // map<Sequence, Packet> 自动处理了排序问题。
                    sendAck(expectedSeq);
                    // 发送重复 ACK (Duplicate ACK)
    // 注意：sendAck 函数内部会自动扫描 recvBuffer 并生成 SACK 块
    // 告诉 Sender：“我虽然想要 expectedSeq，但我后面还收到了别的块”
                }
                // 情况3：收到旧包 (Duplicate)忽略，重发 ACK 即可
                else {
                    sendAck(expectedSeq);
                }
            }
        }
    }
    closesocket(serverSocket);
    WSACleanup();
    return 0;
}