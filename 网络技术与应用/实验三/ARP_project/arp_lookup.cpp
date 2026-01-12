// arp_lookup.cpp
// 编译 (Developer Command Prompt for VS):
// cl /EHsc arp_lookup.cpp /I <npcap-sdk>\Include /link <libpath>\wpcap.lib <libpath>\Packet.lib Ws2_32.lib

#include <winsock2.h>
#include <ws2tcpip.h>
#include <pcap.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#pragma comment(lib, "wpcap.lib")
#pragma comment(lib, "Packet.lib")
#pragma comment(lib, "ws2_32.lib")

// -------------------- 帮助函数 --------------------
void print_mac(const u_char *mac) {
    printf("%02X-%02X-%02X-%02X-%02X-%02X",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

// 将字符串点分IP转换为 uint32_t（网络字节序）
// 返回 0 = 成功, -1 = 失败
int parse_ip(const char *s, uint32_t *out_netorder) {
    struct in_addr addr;
    int r = inet_pton(AF_INET, s, &addr);
    if (r != 1) return -1;
    *out_netorder = addr.s_addr; // already in network byte order
    return 0;
}

// -------------------- 帧结构定义（按字节严格布局） --------------------
#pragma pack(push,1)
typedef struct {
    u_char dst_mac[6];
    u_char src_mac[6];
    uint16_t eth_type; // big-endian (network order)
} eth_hdr_t;

typedef struct {
    uint16_t htype;      // hardware type (1 = Ethernet) - big-endian
    uint16_t ptype;      // protocol type (0x0800 for IPv4) - big-endian
    u_char hlen;         // hardware addr length (6)
    u_char plen;         // protocol addr length (4)
    uint16_t oper;       // operation: 1=request, 2=reply - big-endian
    u_char sha[6];       // sender hardware addr
    uint32_t spa;        // sender protocol addr (IPv4) - network order
    u_char tha[6];       // target hardware addr
    uint32_t tpa;        // target protocol addr (IPv4) - network order
} arp_pkt_t;

typedef struct {
    eth_hdr_t eth;
    arp_pkt_t arp;
} arp_frame_t;
#pragma pack(pop)

// -------------------- 主体程序 --------------------
int main() {
    // 1) 初始化 Winsock（为 inet_pton 安全）
    WSADATA wsd;
    if (WSAStartup(MAKEWORD(2,2), &wsd) != 0) {
        printf("WSAStartup failed\n");
        return 1;
    }

    // 2) 列出设备
    char errbuf[PCAP_ERRBUF_SIZE] = {0};
    pcap_if_t *alldevs = NULL;
    if (pcap_findalldevs(&alldevs, errbuf) == -1) {
        printf("pcap_findalldevs failed: %s\n", errbuf);
        WSACleanup();
        return 1;
    }

    printf("==== Available Network Interfaces ====\n");
    int idx = 0;
    for (pcap_if_t *d = alldevs; d; d = d->next) {
        printf("[%d] %s (%s)\n", ++idx,
               d->name,
               d->description ? d->description : "No description");
    }
    if (idx == 0) {
        printf("No interfaces found.\n");
        pcap_freealldevs(alldevs);
        WSACleanup();
        return 1;
    }

    int choice = 0;
    printf("Select interface index: ");
    scanf("%d", &choice);
    if (choice < 1 || choice > idx) {
        printf("Invalid choice\n");
        pcap_freealldevs(alldevs);
        WSACleanup();
        return 1;
    }

    // 找到选中的设备
    pcap_if_t *dev = alldevs;
    for (int i = 1; i < choice; ++i) dev = dev->next;

    printf("Opening device: %s\n", dev->name);
    // 打开设备（snaplen 65536, 混杂模式, timeout 1000 ms）
    pcap_t *handle = pcap_open_live(dev->name, 65536, 1, 1000, errbuf);
    if (!handle) {
        printf("pcap_open_live failed: %s\n", errbuf);
        pcap_freealldevs(alldevs);
        WSACleanup();
        return 1;
    }

    // 释放设备链表
    pcap_freealldevs(alldevs);

    // 3) 获取本机 MAC 和 IP（从打开的设备的地址列表取第一个 IPv4）
    //    注意：pcap_if_t 里已经有地址列表，但我们释放了 alldevs；所以这里再用 pcap_lookupdev / pcap_lookupnet 或用户输入更可靠。
    // 简单策略：让用户输入本机 IP（因获取本机 IP 在不同 Windows 环境有差异）
    char local_ip_str[64];
    printf("Enter your local interface IP (e.g. 192.168.1.10): ");
    scanf("%s", local_ip_str);

    uint32_t local_ip_net;
    if (parse_ip(local_ip_str, &local_ip_net) != 0) {
        printf("Invalid IP\n");
        pcap_close(handle);
        WSACleanup();
        return 1;
    }

    // 获取本机 MAC：尝试使用 Packet.dll 获取 adapter physical addr
    // 但更简单且稳妥：让用户填写本机 MAC（实验室环境可手动查看 ipconfig /all）
    char local_mac_input[32];
    printf("Enter your local MAC (format: AA-BB-CC-DD-EE-FF) or 00-00-00-00-00-00 to auto (try to auto): ");
    scanf("%s", local_mac_input);

    u_char local_mac[6] = {0};
    bool mac_provided = false;
    if (strcmp(local_mac_input, "00-00-00-00-00-00") != 0) {
        // 解析用户输入的 MAC
        unsigned int b[6];
        if (sscanf(local_mac_input, "%x-%x-%x-%x-%x-%x",
                   &b[0], &b[1], &b[2], &b[3], &b[4], &b[5]) == 6) {
            for (int i = 0; i < 6; ++i) local_mac[i] = (u_char)b[i];
            mac_provided = true;
        } else {
            printf("Bad MAC format\n");
            pcap_close(handle);
            WSACleanup();
            return 1;
        }
    } else {
        // 尝试自动获取 MAC：使用 Packet.dll 的 PacketGetAdapterNames + PacketOpenAdapter + PacketGetAdapterInfo
        // 为简洁这里不实现自动获取；如果你需要自动获取我可以补上示例
        printf("Auto MAC lookup not implemented in this demo. Please provide MAC next time.\n");
        pcap_close(handle);
        WSACleanup();
        return 1;
    }

    // 4) 询问目标 IP
    char target_ip_str[64];
    printf("Enter target IP to resolve (e.g. 192.168.1.20): ");
    scanf("%s", target_ip_str);

    uint32_t target_ip_net;
    if (parse_ip(target_ip_str, &target_ip_net) != 0) {
        printf("Invalid target IP\n");
        pcap_close(handle);
        WSACleanup();
        return 1;
    }

    // 5) 构造 ARP 请求帧
    arp_frame_t frame;
    memset(&frame, 0, sizeof(frame));

    // Ethernet header: dst = broadcast, src = local_mac, eth_type = 0x0806 (ARP)
    for (int i = 0; i < 6; ++i) frame.eth.dst_mac[i] = 0xFF;
    for (int i = 0; i < 6; ++i) frame.eth.src_mac[i] = local_mac[i];
    frame.eth.eth_type = htons(0x0806); // ARP

    // ARP payload
    frame.arp.htype = htons(1);          // Ethernet
    frame.arp.ptype = htons(0x0800);     // IPv4
    frame.arp.hlen = 6;
    frame.arp.plen = 4;
    frame.arp.oper = htons(1);           // ARP request

    // Sender hardware addr (our MAC)
    memcpy(frame.arp.sha, local_mac, 6);
    // Sender protocol addr (our IP) - already net order
    frame.arp.spa = local_ip_net;
    // Target hardware addr: zeros for request
    memset(frame.arp.tha, 0x00, 6);
    // Target protocol addr: target IP (net order)
    frame.arp.tpa = target_ip_net;

    // 6) 发送 ARP 请求（多次以提高可靠性）
    int send_count = 3;
    for (int i = 0; i < send_count; ++i) {
        if (pcap_sendpacket(handle, (const u_char*)&frame, sizeof(frame)) != 0) {
            printf("pcap_sendpacket error: %s\n", pcap_geterr(handle));
        }
    }
    printf("ARP requests sent, waiting for reply...\n");

    // 7) 捕获 ARP 回复（循环，带超时）
    int timeout_ms = 5000; // 总超时 5 秒
    int elapsed = 0;
    const int poll_interval = 100; // ms
    bool found = false;
    u_char errBuff[PCAP_ERRBUF_SIZE];

    while (elapsed < timeout_ms && !found) {
        struct pcap_pkthdr *pkt_header;
        const u_char *pkt_data;
        int res = pcap_next_ex(handle, &pkt_header, &pkt_data);
        if (res == 0) {
            // timeout in libpcap; wait a bit and loop
            Sleep(poll_interval);
            elapsed += poll_interval;
            continue;
        } else if (res == 1) {
            // got a packet
            if (pkt_header->len < sizeof(eth_hdr_t) + sizeof(arp_pkt_t)) continue;
            const eth_hdr_t *reh = (const eth_hdr_t*)pkt_data;
            uint16_t ether_type = ntohs(reh->eth_type);
            if (ether_type != 0x0806) continue; // not ARP

            const arp_pkt_t *rap = (const arp_pkt_t*)(pkt_data + sizeof(eth_hdr_t));
            uint16_t op = ntohs(rap->oper);
            // interested in ARP reply (op == 2), and sender protocol addr equals target_ip
            if (op == 2 && rap->spa == target_ip_net) {
                printf("Got ARP reply:\n");
                printf("Sender IP: %s\n", target_ip_str);
                printf("Sender MAC: ");
                print_mac(rap->sha);
                printf("\n");
                found = true;
                break;
            }
        } else if (res == -1) {
            printf("pcap_next_ex error: %s\n", pcap_geterr(handle));
            break;
        } else if (res == -2) {
            printf("pcap_next_ex: EOF or loop terminated\n");
            break;
        }
    }

    if (!found) {
        printf("No ARP reply received within %d ms\n", timeout_ms);
    }

    pcap_close(handle);
    WSACleanup();
    return 0;
}
