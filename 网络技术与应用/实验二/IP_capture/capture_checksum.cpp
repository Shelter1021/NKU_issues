// capture_checksum.cpp
// Windows (MSVC) + NPcap (wpcap.lib, Packet.lib) example
// 功能：抓取以太网帧 -> 若为 IPv4 则打印 MAC/IP、报文内 IP header checksum 与程序计算 checksum 并比较

#include <winsock2.h>
#include <ws2tcpip.h>
#include <pcap.h>
#include <stdio.h>
#include <stdint.h>

#pragma comment(lib, "wpcap.lib")
#pragma comment(lib, "Packet.lib")
#pragma comment(lib, "Ws2_32.lib")

// 打印 MAC 地址 (6 bytes)
void print_mac(const u_char *mac) {
    printf("%02X:%02X:%02X:%02X:%02X:%02X",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

// 计算 IPv4 头部校验和；hdr 指向 IP header 的起始字节，ihl_bytes 为头长（字节）
uint16_t compute_ip_checksum(const u_char *hdr, int ihl_bytes) {
    uint32_t sum = 0;
    // 以 16-bit 单位累加，校验字段需视为 0（hdr[10],hdr[11]）
    for (int i = 0; i < ihl_bytes; i += 2) {
        // 跳过校验和字段（字节10和11）
        if (i == 10) {
            continue;
        }
        uint16_t word = (hdr[i] << 8) | hdr[i + 1];
        sum += (uint32_t)word;
    }
    // 若 ihl_bytes 为奇数（实际 IPv4 header 应为偶数），这里做一般化处理：
    if (ihl_bytes % 2 == 1) { // unlikely for IPv4, but safe
        uint16_t last = hdr[ihl_bytes - 1] << 8;
        sum += last;
    }
    // 将溢出高位回卷
    while (sum >> 16) {
        sum = (sum & 0xFFFF) + (sum >> 16);
    }
    uint16_t result = (uint16_t)(~sum & 0xFFFF);
    return result;
}

void packet_handler(u_char *user, const struct pcap_pkthdr *h, const u_char *bytes) {
    (void)user;
    // 最少需要以太网头（14字节）和 IP 固定最小头（20字节）
    if (h->len < 14 + 20) return;

    const u_char *eth = bytes;
    uint16_t eth_type = (eth[12] << 8) | eth[13];
    if (eth_type != 0x0800) { // 0x0800 = IPv4
        return;
    }

    const u_char *ip = bytes + 14;
    // ip[0]: version(高4位) + ihl(低4位)
    int ihl = ip[0] & 0x0F;         // header length in 32-bit words
    int ihl_bytes = ihl * 4;
    if (ihl_bytes < 20) return;     // 非法头

    // 报文中原始校验和（网络字节序）
    uint16_t checksum_in = (ip[10] << 8) | ip[11];

    // 计算校验和
    uint16_t checksum_calc = compute_ip_checksum(ip, ihl_bytes);

    // 打印信息 - 使用最简单的英文输出
    printf("---- Packet captured (len=%u) ----\n", (unsigned)h->len);
    printf("Dest MAC: "); print_mac(eth + 0); printf("\n");
    printf("Src  MAC: "); print_mac(eth + 6); printf("\n");

    // 源/目的 IP
    char src_ip[INET_ADDRSTRLEN] = {0};
    char dst_ip[INET_ADDRSTRLEN] = {0};
    // ip bytes ip+12..ip+15 / ip+16..ip+19
    sprintf_s(src_ip, sizeof(src_ip), "%u.%u.%u.%u", ip[12], ip[13], ip[14], ip[15]);
    sprintf_s(dst_ip, sizeof(dst_ip), "%u.%u.%u.%u", ip[16], ip[17], ip[18], ip[19]);
    printf("Src IP: %s\n", src_ip);
    printf("Dst IP: %s\n", dst_ip);

    printf("Header IHL: %d bytes\n", ihl_bytes);
    printf("IP header checksum (in packet): 0x%04X\n", checksum_in);
    printf("IP header checksum (calc):      0x%04X\n", checksum_calc);
    
    // 最简单的英文输出，避免任何特殊字符
    if (checksum_in == checksum_calc) {
        printf("Checksum: OK\n");
    } else {
        printf("Checksum: FAIL\n");
    }
    printf("\n");
}

int main() {
    char errbuf[PCAP_ERRBUF_SIZE] = {0};
    pcap_if_t *alldevs = NULL;
    int index = 0;

    if (pcap_findalldevs(&alldevs, errbuf) == -1) {
        printf("pcap_findalldevs failed: %s\n", errbuf);
        return 1;
    }

    // 列出现有网卡
    printf("==== Available Network Interfaces ====\n");
    pcap_if_t *d;
    for (d = alldevs; d; d = d->next) {
        printf("[%d] %s (%s)\n", ++index, d->name,
               d->description ? d->description : "No description");
    }

    if (index == 0) {
        printf("No interfaces found! Ensure NPcap is installed.\n");
        return 1;
    }

    // 让用户选择网卡编号
    int choice;
    printf("\nSelect interface index: ");
    scanf_s("%d", &choice);

    // 找到用户选择的网卡
    index = 0;
    for (d = alldevs; d; d = d->next) {
        if (++index == choice) break;
    }

    if (!d) {
        printf("Invalid choice.\n");
        pcap_freealldevs(alldevs);
        return 1;
    }

    printf("\nOpening device: %s (%s)\n", d->name, d->description ? d->description : "No desc");

    pcap_t *handle = pcap_open_live(d->name, 65536, 1, 1000, errbuf);
    if (!handle) {
        printf("pcap_open_live failed: %s\n", errbuf);
        pcap_freealldevs(alldevs);
        return 1;
    }

    pcap_freealldevs(alldevs);

    // 使用 IP 过滤器提升效率
    struct bpf_program fp;
    if (pcap_compile(handle, &fp, "ip", 1, PCAP_NETMASK_UNKNOWN) == 0) {
        pcap_setfilter(handle, &fp);
        pcap_freecode(&fp);
    }

    printf("\nStart capturing... (move mouse / open webpage to generate packets)\n");
    printf("Press Ctrl+C to stop.\n\n");
    
    pcap_loop(handle, -1, packet_handler, NULL);

    pcap_close(handle);
    return 0;
}
