#include "common.h"
#include <iomanip>

// 全局变量
SOCKET clientSocket;
SOCKADDR_IN routerAddr;
int routerAddrLen = sizeof(routerAddr);

// [实验要求(5): 拥塞控制] RENO 状态定义
enum CongestionState { SLOW_START, CONGESTION_AVOIDANCE, FAST_RECOVERY };
CongestionState state = SLOW_START; // 初始状态

// [实验要求(5): 拥塞控制] 核心参数
double cwnd = 1.0;          // 拥塞窗口 (Congestion Window):：控制发送速率
double ssthresh = 16.0;     // 慢启动阈值:决定何时从指数增长切换为线性增长
int dupACKcount = 0;        // 重复ACK计数 (用于触发快重传):专门用于检测“快重传”时机

// [实验要求(4): 流量控制] 接收窗口
unsigned int rwnd = 100;    // 接收方通告的窗口大小 (初始化为一个较大值)

// [实验要求(3): 确认重传] 滑动窗口与流水线
unsigned int base = 0;      // 窗口基准 (最早未确认的包)
unsigned int nextSeq = 0;   // 下一个待发送的序号
std::vector<Packet> packetBuffer; // 发送缓冲区 (存储文件内容)

// 统计变量 (用于计算丢包率)
long long totalSendCount = 0;

// 计时器
clock_t timerStart;
bool timerRunning = false;
const double TIMEOUT_INTERVAL = 1.0; // 超时时间 (秒)

// 发送数据包封装函数
// [实验要求(2): 差错检测] 发送前计算校验和
void sendPacket(Packet& pkt) {
    // ==========================================
    // [差错检测] 生成校验和
    // ==========================================
    // 在发送前，调用 common.h 里的算法。
    // 此时 pkt 里的 checkSum 字段是垃圾值或0。
    // 函数内部会先清零计算，然后返回正确的值。
    // 我们把计算结果赋值给 header.checkSum，这就是“盖章”过程。
    pkt.header.checkSum = calculateChecksum(&pkt);
    sendto(clientSocket, (char*)&pkt, sizeof(Header) + pkt.header.length, 0, (SOCKADDR*)&routerAddr, routerAddrLen);
    // 调用 Socket API 发送数据
    // 发送长度 = 头部大小 + 数据有效载荷长度
    // [统计] 增加发送计数
    totalSendCount++;
}

// 可视化：进度条与状态显示
void printInfo(int current, int total, double elapsed) {
    int barWidth = 40;
    float progress = (float)current / total;
    if (progress > 1.0) progress = 1.0;
    int pos = (int)(barWidth * progress);

    printf("\r[");
    for (int i = 0; i < barWidth; ++i) {
        if (i < pos) printf("=");
        else if (i == pos) printf(">");
        else printf(" ");
    }
    // [实验要求: 日志详细提示] 实时显示 CWND 和 状态 和 RWND
    printf("] %3d%% | CWND:%.1f | RWND:%u | State:%s",
        (int)(progress * 100.0), cwnd, rwnd,
        state == SLOW_START ? "SlowStart" : (state == CONGESTION_AVOIDANCE ? "CongAvoid" : "FastRecov"));
}

// [实验要求(1): 连接管理] 
// 三次握手发送端主动发起连接和断开连接。代码主要集中在 handshake() 和 teardown() 函数中。
bool handshake() {
    printf("\n[Log] --- Start 3-Way Handshake ---\n");

    // ==========================================
     // 第一次握手：客户端发送 SYN
     // ==========================================
    Packet synPkt;
    memset(&synPkt, 0, sizeof(synPkt));
    synPkt.header.flags = FLAG_SYN;// [关键] 设置 SYN 标志位，表示请求建立连接
    synPkt.header.seq = 0;// 初始序列号 (ISN) 设为 0
    sendPacket(synPkt);// 封装并发送数据包
    printf("[Log] Send SYN (Seq=0)\n");

    Packet recvPkt;
    clock_t start = clock();// 启动计时器，用于超时检测

    // ==========================================
    // 异常处理：超时重传机制
    // ==========================================
    while (true) {
        // 如果在 2秒内 没有收到服务器的回复，说明 SYN 包丢失或服务器未响应
        if ((double)(clock() - start) / CLOCKS_PER_SEC > 2.0) {
            printf("\n[Exception] Handshake Timeout. Retrying SYN...\n");
            sendPacket(synPkt);// 重传 SYN 包
            start = clock();// 重置计时器
        }
        // 使用 select 非阻塞模式检查是否有数据到达
        fd_set readfds;
        FD_ZERO(&readfds);
        FD_SET(clientSocket, &readfds);
        timeval tv = { 0, 100000 };// 100ms 轮询
        int ret = select(0, &readfds, NULL, NULL, &tv);

        if (ret > 0) {
            SOCKADDR_IN tempAddr;
            int tempLen = sizeof(tempAddr);
            int len = recvfrom(clientSocket, (char*)&recvPkt, sizeof(Packet), 0, (SOCKADDR*)&tempAddr, &tempLen);
            if (len > 0) {
                // 校验和检查，确保包没坏
                if (calculateChecksum(&recvPkt) == recvPkt.header.checkSum) {
                    // ==========================================
                    // 第二次握手处理：收到 SYN + ACK
                    // ==========================================
                    // 检查对方是否同时也设置了 SYN 和 ACK 标志
                    if ((recvPkt.header.flags & FLAG_SYN) && (recvPkt.header.flags & FLAG_ACK)) {
                        printf("[Log] Recv SYN+ACK. Handshake Step 2 OK.\n");
                        break;// 握手第二步成功，跳出循环，进行第三步
                    }
                }
            }
        }
    }

    // ==========================================
     // 第三次握手：客户端发送 ACK
     // ==========================================
    Packet ackPkt;
    memset(&ackPkt, 0, sizeof(ackPkt));
    ackPkt.header.flags = FLAG_ACK;// 设置 ACK 标志
    ackPkt.header.seq = 1;// 下一个序列号
    ackPkt.header.ack = recvPkt.header.seq + 1;// 确认号 = 对方Seq + 1
    sendPacket(ackPkt);
    printf("[Log] Send ACK. Connection Established.\n");

    // [状态初始化] 握手成功后，初始化滑动窗口、拥塞控制参数等
    base = 1;//最早发出去、但还没有收到确认（ACK）的那个包的序号
    nextSeq = 1;//下一个待发送序号
    cwnd = 1.0;//拥塞窗口 
    ssthresh = 16.0;//慢启动阈值
    rwnd = 100; // 初始假设接收窗口很大
    state = SLOW_START;// 初始状态为慢启动
    dupACKcount = 0;//重复 ACK 计数器,累加到3触发 快重传
    totalSendCount = 0; // 重置统计

    return true;
}

// [实验要求(1): 连接管理] 四次挥手
void teardown() {
    printf("\n[Log] --- Start 4-Way Teardown ---\n");

    // ==========================================
     // 第一次挥手：客户端发送 FIN
     // ==========================================
    Packet finPkt;
    memset(&finPkt, 0, sizeof(finPkt));
    finPkt.header.flags = FLAG_FIN;// [关键] 设置 FIN 标志，表示数据发完了
    finPkt.header.seq = nextSeq;// 序列号接在数据后面
    sendPacket(finPkt);
    printf("[Log] Send FIN\n");

    bool finAckReceived = false;// 对方是否确认了我的 FIN
    bool finReceived = false;// 我是否收到了对方的 FIN
    Packet recvPkt;
    clock_t start = clock();

    // 等待过程：需要等待服务器的 ACK 和服务器的 FIN
    while (!finAckReceived || !finReceived) {
        // [异常处理] 挥手超时,强制退出
        if ((double)(clock() - start) / CLOCKS_PER_SEC > 5.0) {
            printf("\n[Exception] Teardown Timeout. Force closing.\n");
            break;
        }
        // 非阻塞接收
        u_long mode = 1; ioctlsocket(clientSocket, FIONBIO, &mode);
        SOCKADDR_IN tempAddr; int tempLen = sizeof(tempAddr);
        int len = recvfrom(clientSocket, (char*)&recvPkt, sizeof(Packet), 0, (SOCKADDR*)&tempAddr, &tempLen);

        if (len > 0) {
            // ==========================================
            // 第二次挥手处理：收到 ACK
            // ==========================================
            if (recvPkt.header.flags & FLAG_ACK) {
                finAckReceived = true;// 服务器确认收到我的断开请求
            }
            // ==========================================
            // 第三次挥手处理：收到 FIN (服务器也请求断开)
            // ==========================================
            if (recvPkt.header.flags & FLAG_FIN) {
                finReceived = true;
                printf("\n[Log] Recv FIN from Server\n");
                // ==========================================
                // 第四次挥手：发送最后的 ACK
                // ==========================================
                Packet lastAck;
                memset(&lastAck, 0, sizeof(lastAck));
                lastAck.header.flags = FLAG_ACK;
                sendPacket(lastAck);// 告诉服务器我知道你也断开了
            }
            start = clock();// 收到包就重置超时计时
        }
    }
    u_long mode = 0; ioctlsocket(clientSocket, FIONBIO, &mode);
    printf("[Log] Connection Closed.\n");
}

bool loadFile(const std::string& filename) {
    packetBuffer.clear();
    FILE* fp = nullptr;
    fopen_s(&fp, filename.c_str(), "rb");
    if (!fp) {
        printf("[Error] Cannot open file: %s\n", filename.c_str());
        return false;
    }

    int seqCounter = 1;
    char buffer[MSS];
    int bytesRead;
    while ((bytesRead = fread(buffer, 1, MSS, fp)) > 0) {
        Packet pkt;
        memset(&pkt, 0, sizeof(pkt));
        pkt.header.seq = seqCounter++;
        pkt.header.length = bytesRead;
        pkt.header.flags = 0;
        memcpy(pkt.data, buffer, bytesRead);
        packetBuffer.push_back(pkt);
    }
    fclose(fp);
    Packet last; last.header.seq = seqCounter; last.header.length = 0;
    packetBuffer.push_back(last);

    printf("[Info] File loaded. Size: %llu packets\n", packetBuffer.size() - 1);
    return true;
}

// [实验要求(5): 拥塞控制] RENO 算法核心实现
void updateCongestionControl(char event) {
    if (event == 'N') { // New ACK (收到新确认)
        if (state == SLOW_START) {
            // ==========================================
        // [状态：慢启动] -> 指数增长
        // ==========================================
        // 每收到一个 ACK，窗口加 1。
        // 比如：发1个回1个->变2，发2个回2个->变4。
            cwnd += 1.0;
            // [状态切换] 达到阈值，切换到“拥塞避免”
            if (cwnd >= ssthresh) state = CONGESTION_AVOIDANCE;
        }
        else if (state == CONGESTION_AVOIDANCE) {
            // ==========================================
         // [状态：拥塞避免] -> 线性增长 (加性增)
         // ==========================================
         // 目标：每过一个 RTT (即发完一整窗数据)，窗口只加 1。
         // 实现：每收到一个 ACK，窗口增加 1/cwnd。
            cwnd += 1.0 / cwnd;
        }
        else if (state == FAST_RECOVERY) {
            // ==========================================
        // [状态：快恢复] -> 退出恢复，进入拥塞避免
        // ==========================================
        // 既然收到了新 ACK，说明丢失的包重传成功了，且后续积压的包也确认了。
        // 恢复正常工作状态：
            state = CONGESTION_AVOIDANCE;
            cwnd = ssthresh;// 窗口设为阈值大小 (即减半后的值)
        }
        dupACKcount = 0;// 成功收到新数据确认，重置重复 ACK 计数
    }
    else if (event == 'D') { // Duplicate ACK (收到重复确认)
        if (state == FAST_RECOVERY) {
            cwnd += 1.0; 
            // ==========================================
        // [状态：快恢复] -> 窗口膨胀
        // ==========================================
        // 在快恢复期间，每收到一个重复 ACK，说明网络中又有一个包被接收端收到了(虽然是乱序)。
        // 为了维持流水线，我们临时增大 cwnd，尝试多发一个新包。
        }
        else {
            dupACKcount++;// 在 慢启动 或 拥塞避免 状态下收到重复 ACK
            if (dupACKcount == 3) {
                
                // ==========================================
            // [考点：快重传 & 快恢复触发]
            // ==========================================
            // 收到 3 个冗余 ACK，不再等待超时，立即认定 base 包丢失。
                printf("\n[RENO] Fast Retransmit Triggered! Resend Seq=%u\n", base);
                state = FAST_RECOVERY;// 2. 进入快恢复状态
                // 1. 乘性减 (Multiplicative Decrease)
            // 阈值设为当前窗口的一半 (至少为2)
                ssthresh = max(cwnd / 2.0, 2.0); // 乘性减
                cwnd = ssthresh + 3.0;
                // 3. 设置新窗口
            // RENO 算法规定：cwnd = ssthresh + 3
            // (+3 是为了补偿刚才收到的 3 个重复 ACK，允许发 3 个新包)
                // 立即重传丢失的包
                if (base - 1 < packetBuffer.size()) {
                    sendPacket(packetBuffer[base - 1]);
                }
            }
        }
    }
    else if (event == 'T') { // Timeout (超时)
        printf("\n[RENO] Timeout Occurred! Seq=%u\n", base);
        // [超时处理]: 门限减半，cwnd置1，进入慢启动
        // ==========================================
    // [考点：超时处理]
    // ==========================================
    // 1. 保存当前状态的一半作为新阈值
        ssthresh = max(cwnd / 2.0, 2.0);
        cwnd = 1.0;// 2. 窗口一夜回到解放前 (置 1)
        state = SLOW_START;// 3. 重新进入慢启动
        dupACKcount = 0;// 4. 归零计数

        if (base - 1 < packetBuffer.size()) {// 5. 立即重传
            sendPacket(packetBuffer[base - 1]);// 重置计时器
            timerStart = clock();
        }
    }
    if (cwnd < 1.0) cwnd = 1.0;
}
//3和4
void sendData() {
    clock_t startTime = clock();
    int totalPackets = packetBuffer.size() - 1;
    int totalBytesSent = 0;

    // 重置统计
    totalSendCount = 0;

    u_long mode = 1;
    ioctlsocket(clientSocket, FIONBIO, &mode);

    printf("\n");

    // [实验要求(3): 确认重传] 支持流水线方式
    // 这里的 while 循环体现了流水线机制。
    // 只要 nextSeq (下一个待发序号) 在 窗口范围 (base + window) 内，
    // 就不停地发，不等待 ACK。
    while (base < packetBuffer.size()) {
        double elapsed = (double)(clock() - startTime) / CLOCKS_PER_SEC;
        printInfo(base - 1, totalPackets, elapsed);

        // [实验要求(4): 流量控制] 发送窗口控制：受限于 cwnd 和 rwnd 的最小值
        // 确保 rwnd 至少为 1，避免死锁 (实际TCP会有 persist timer，这里简化处理)
        // ==========================================
    // [流量控制 - 核心步骤 3] 确定有效发送窗口
    // ==========================================
    // 这里的逻辑非常关键，体现了 TCP 的双重限制：
    // 1. cwnd (拥塞窗口): 限制网络不被塞满
    // 2. rwnd (接收窗口): 限制接收方不被塞满
    // 我们取两者的 最小值 (min)作为实际能发的窗口大小。
        //感知变化：在 receiver.cpp 中，我并没有把接收能力写死成一个固定值。每次发送 ACK 前，我都会计算当前缓冲区 recvBuffer 占用了多少字节（usedBytes）。

       // 实时计算：我用固定的总物理空间减去当前已占用的空间，算出了实时的剩余空间(freeSpace)。

          //  动态反馈：这个剩余空间的值会被填入 ACK 头部发给发送方。如果缓冲区快满了，这个值会接近 0；如果缓冲区被清空写入文件了，这个值会迅速回升。

           // 发送端响应：发送端收到后，通过 min(cwnd, rwnd) 实时调整发送窗口。
        unsigned int effectiveWindow = min((unsigned int)cwnd, rwnd);
        // [死锁预防] 
    // 如果 effectiveWindow 变成 0 (接收方满了)，按理说不能发数据了。
    // 但如果完全不发，Sender 就不知道 Receiver 什么时候有空位了（假设 Receiver 的窗口更新包丢了）。
    // 所以 TCP 标准做法是：如果窗口为 0，依然允许发送 1 个字节的探测包 (Persist Timer)。
    // 这里做了简化：强制窗口至少为 1，慢速重试，防止死锁。
        if (effectiveWindow < 1) effectiveWindow = 1;
        // ==========================================
    // [发送判断]
    // ==========================================
    // 只有当 nextSeq 在这个 effectiveWindow 范围内时，才允许发送。
    // 如果 rwnd 很小，effectiveWindow 就会很小，nextSeq 就无法增长，
    // 发送循环就会暂停，从而实现了“流量控制”。
        while (nextSeq < base + effectiveWindow && nextSeq <= packetBuffer.size() - 1) {
            Packet& pkt = packetBuffer[nextSeq - 1];
            sendPacket(pkt);// 发送数据
            totalBytesSent += pkt.header.length;
            // 如果是当前窗口的第一个包，启动超时计时器
        // (TCP 标准：只对最早未确认的包计时)
            if (base == nextSeq) {
                timerStart = clock();
                timerRunning = true;
            }
            nextSeq++;// 准备发下一个
        }

        // 接收 ACK
        Packet recvPkt;
        SOCKADDR_IN tempAddr;
        int tempLen = sizeof(tempAddr);
        int len = recvfrom(clientSocket, (char*)&recvPkt, sizeof(Packet), 0, (SOCKADDR*)&tempAddr, &tempLen);

        if (len > 0) {
            // [实验要求(2): 差错检测]
            if (calculateChecksum(&recvPkt) == recvPkt.header.checkSum && (recvPkt.header.flags & FLAG_ACK)) {
                unsigned int ackNum = recvPkt.header.ack;

                // [实验要求(4): 流量控制] 更新接收窗口大小
                rwnd = recvPkt.header.recvWindow;

                // [实验要求(3): 选择确认] 打印SACK信息
               // ==========================================
        // SACK 构建：接收端在回复 ACK 时，会遍历缓冲区，计算出连续的数据块（SACK Blocks）
        // 告诉发送方‘虽然缺了第 N 号包，但 N+1 到 N+5 我都已经收到了’
        // ==========================================
        // 虽然 Sender 主要靠 base 和 dupACK 重传，
        // 但解析 SACK 能让我们看到 Receiver 到底收到了哪些乱序块。
                if (recvPkt.header.sackCount > 0) {
                    printf("\n[SACK Info] Recv ACK:%u, SACK Blocks: ", ackNum);
                    for (int i = 0; i < recvPkt.header.sackCount; i++) {
                        printf("[%u-%u] ", recvPkt.header.sackBlocks[i][0], recvPkt.header.sackBlocks[i][1]);
                    }
                    printf("\n");
                }
                // ==========================================
               // [考点：滑动窗口更新]
               // ==========================================
                if (ackNum > base) {

                    // 收到新的 ACK (New ACK)
                     // 窗口基准右移 (Slide Window)
                    base = ackNum;
                    // 更新拥塞控制状态 (清除重复ACK计数)
                    updateCongestionControl('N');
                    // 重置计时器 (因为 base 变了，针对新的 base 重新计时)
                    timerRunning = true;
                    timerStart = clock();
                    // 如果所有包都确认了，停止计时
                    if (base >= nextSeq) timerRunning = false;
                }
                else {
                   // ==========================================
            // [考点：快速重传触发]
            // 发送端结合了超时重传和快重传。当收到 3 个重复 ACK（通常带有 SACK 信息）时，
            // 立即重传丢失的基准包，而无需等待超时
            // ==========================================
            // 收到重复 ACK (Duplicate ACK)
            // 意味着 base 号包丢失了，但后面的包到了 (所以接收方发回了含 SACK 的重复 ACK)
            // 注意：updateCongestionControl('D') 内部在收到 3 个重复 ACK 时，
            // 会直接重传 base 号包，不需要等超时。
                    updateCongestionControl('D');
                }
            }
        }

        // 超时检测
        if (timerRunning && ((double)(clock() - timerStart) / CLOCKS_PER_SEC > TIMEOUT_INTERVAL)) {
            updateCongestionControl('T');
        }
    }

    mode = 0; ioctlsocket(clientSocket, FIONBIO, &mode);

    // [实验要求(5)] 显示传输时间和平均吞吐率
    printInfo(totalPackets, totalPackets, (double)(clock() - startTime) / CLOCKS_PER_SEC);

    clock_t endTime = clock();
    double duration = (double)(endTime - startTime) / CLOCKS_PER_SEC;
    double throughput = (totalBytesSent / 1024.0) / duration; // KB/s

    // [统计] 计算丢包率 (重传数/总发包数)
    double lossRate = 0.0;
    if (totalSendCount > 0 && totalSendCount >= totalPackets) {
        lossRate = (double)(totalSendCount - totalPackets) / totalSendCount * 100.0;
    }
    if (lossRate < 0) lossRate = 0;

    printf("\n\n=========================================\n");
    printf("[Success] File Transfer Complete!\n");
    printf("Total Time     : %.2f s\n", duration);
    printf("Total Bytes    : %d B\n", totalBytesSent);
    printf("Avg Throughput : %.2f KB/s\n", throughput);
    printf("Est. Loss Rate : %.2f %% (Retransmissions included)\n", lossRate);
    printf("=========================================\n");
}

int main() {
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2, 2), &wsaData);

    clientSocket = socket(AF_INET, SOCK_DGRAM, 0);

    // 配置发往路由器的地址
    routerAddr.sin_family = AF_INET;
    routerAddr.sin_port = htons(ROUTER_PORT); // 8000
    inet_pton(AF_INET, SERVER_IP, &routerAddr.sin_addr);

    printf("[System] Sender initialized. Target: Router (Port %d)\n", ROUTER_PORT);

    // [实验要求] 不重启程序就能连续发送
    while (true) {
        std::string filename;
        printf("\n=========================================\n");
        printf("Sender Ready. Enter filename (e.g., 1.jpg) or 'exit': ");
        std::cin >> filename;

        if (filename == "exit") break;

        if (!loadFile(filename)) continue;

        if (handshake()) {
            sendData();
            teardown();
        }
        else {
            printf("[Error] Handshake failed. Check connection.\n");
        }
    }

    closesocket(clientSocket);
    WSACleanup();
    return 0;
}