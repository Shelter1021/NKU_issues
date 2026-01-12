#define _CRT_SECURE_NO_WARNINGS
#define _WINSOCK_DEPRECATED_NO_WARNINGS

#include <pcap.h>
#include <winsock2.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#pragma comment(lib, "wpcap.lib")
#pragma comment(lib, "Packet.lib")
#pragma comment(lib, "ws2_32.lib")

#define MAX_ARP     50
#define MAX_BUFFER  50

// ======================= Ethernet / ARP / IP structures =======================
#pragma pack(push, 1)

// Ethernet header
typedef struct _ETH_HEADER {
    BYTE dest[6];
    BYTE src[6];
    WORD type;
} ETH_HEADER;

// ARP packet
typedef struct _ARP_PACKET {
    ETH_HEADER eth;
    WORD htype;
    WORD ptype;
    BYTE hlen;
    BYTE plen;
    WORD oper;
    BYTE sha[6];
    ULONG spa;
    BYTE tha[6];
    ULONG tpa;
} ARP_PACKET;

// IP header (no options)
typedef struct _IP_HEADER {
    BYTE ver_ihl;      // high 4 bits: version, low 4 bits: IHL
    BYTE tos;
    WORD tot_len;
    WORD id;
    WORD frag_off;
    BYTE ttl;
    BYTE protocol;
    WORD check;
    ULONG saddr;
    ULONG daddr;
} IP_HEADER;

#pragma pack(pop)

// ======================= ARP table / route table / buffer =======================

// ARP entry
typedef struct _ARP_ENTRY {
    ULONG ip;
    BYTE mac[6];
    int  used;
} ARP_ENTRY;

// buffered packets waiting for ARP
typedef struct _BUFFER_ENTRY {
    BYTE  data[2000];
    int   len;
    ULONG dest_ip;   // IP whose MAC we need
    int   used;
    clock_t ts;
} BUFFER_ENTRY;

// route table item
typedef struct _ROUTE_ITEM {
    ULONG netmask;
    ULONG destnet;
    ULONG nexthop;   // 0 means directly connected
    int   type;      // 0 direct, 1 static
    struct _ROUTE_ITEM* next;
} ROUTE_ITEM;

typedef struct _ROUTE_TABLE {
    ROUTE_ITEM* head;
    int count;
} ROUTE_TABLE;

// ======================= globals =======================

pcap_t* g_adhandle = NULL;

BYTE  g_my_mac[6] = { 0 };
char  g_my_ip_str[2][16];
char  g_my_mask_str[2][16];
ULONG g_my_ip[2] = { 0 };
ULONG g_my_mask[2] = { 0 };
int   g_ip_count = 0;

ARP_ENTRY    g_arp_table[MAX_ARP];
BUFFER_ENTRY g_buffer[MAX_BUFFER];

// ======================= helper functions =======================

// print IPv4 address
void print_ip(ULONG ip) {
    struct in_addr addr;
    addr.S_un.S_addr = ip;
    printf("%s", inet_ntoa(addr));
}

// init tables
void arp_init() {
    int i;
    for (i = 0; i < MAX_ARP; ++i) {
        g_arp_table[i].used = 0;
        g_arp_table[i].ip = 0;
    }
}

void buffer_init() {
    int i;
    for (i = 0; i < MAX_BUFFER; ++i) {
        g_buffer[i].used = 0;
        g_buffer[i].len = 0;
        g_buffer[i].dest_ip = 0;
        g_buffer[i].ts = 0;
    }
}

// ARP table: search
int arp_find(ULONG ip, BYTE mac[6]) {
    int i, j;
    for (i = 0; i < MAX_ARP; ++i) {
        if (g_arp_table[i].used && g_arp_table[i].ip == ip) {
            for (j = 0; j < 6; ++j) mac[j] = g_arp_table[i].mac[j];
            return 1;
        }
    }
    return 0;
}

// ARP table: add/update
void arp_add(ULONG ip, const BYTE mac[6]) {
    int i, j;
    // update if exists
    for (i = 0; i < MAX_ARP; ++i) {
        if (g_arp_table[i].used && g_arp_table[i].ip == ip) {
            for (j = 0; j < 6; ++j) g_arp_table[i].mac[j] = mac[j];
            return;
        }
    }
    // find empty
    for (i = 0; i < MAX_ARP; ++i) {
        if (!g_arp_table[i].used) {
            g_arp_table[i].used = 1;
            g_arp_table[i].ip = ip;
            for (j = 0; j < 6; ++j) g_arp_table[i].mac[j] = mac[j];
            return;
        }
    }
    // overwrite first one if full
    g_arp_table[0].used = 1;
    g_arp_table[0].ip = ip;
    for (j = 0; j < 6; ++j) g_arp_table[0].mac[j] = mac[j];
}

// add to buffer
void buffer_add(const BYTE* data, int len, ULONG dest_ip) {
    int i;
    for (i = 0; i < MAX_BUFFER; ++i) {
        if (!g_buffer[i].used) {
            memcpy(g_buffer[i].data, data, len);
            g_buffer[i].len = len;
            g_buffer[i].dest_ip = dest_ip;
            g_buffer[i].ts = clock();
            g_buffer[i].used = 1;
            printf("Cache one packet, target IP: ");
            print_ip(dest_ip);
            printf("\n");
            return;
        }
    }
    printf("Buffer is full, drop packet.\n");
}

// send buffered packets for a given IP
void buffer_try_send_for_ip(ULONG ip, const BYTE mac[6]);

// check buffer timeout
void buffer_check_timeout() {
    clock_t now = clock();
    int i;
    for (i = 0; i < MAX_BUFFER; ++i) {
        if (g_buffer[i].used && (now - g_buffer[i].ts) >= 6000) {
            printf("Buffer packet to ");
            print_ip(g_buffer[i].dest_ip);
            printf(" timeout, drop.\n");
            g_buffer[i].used = 0;
        }
    }
}

// IP header checksum
unsigned short ip_checksum(unsigned short* buffer, int size) {
    unsigned long cksum = 0;
    while (size > 1) {
        cksum += *buffer++;
        size -= 2;
    }
    if (size) {
        cksum += *(unsigned char*)buffer;
    }
    cksum = (cksum >> 16) + (cksum & 0xFFFF);
    cksum += (cksum >> 16);
    return (unsigned short)(~cksum);
}

// validate IP header checksum
int ip_header_valid(IP_HEADER* ip) {
    int ihl = (ip->ver_ihl & 0x0F) * 4;
    unsigned short sum = ip_checksum((unsigned short*)ip, ihl);
    return (sum == 0);
}

// choose which local IP to use when sending ARP
int choose_if_for_ip(ULONG ip) {
    int i;
    for (i = 0; i < g_ip_count; ++i) {
        if ((ip & g_my_mask[i]) == (g_my_ip[i] & g_my_mask[i])) {
            return i;
        }
    }
    return 0;
}

// ======================= route table =======================

void rt_init(ROUTE_TABLE* rt) {
    rt->head = NULL;
    rt->count = 0;
}

void rt_print(ROUTE_TABLE* rt) {
    printf("<============== Routing Table ==============>\n");
    ROUTE_ITEM* cur = rt->head;
    int idx = 1;
    while (cur) {
        printf("[Entry %d] Type: %s\n", idx, (cur->type == 0) ? "Direct" : "Static");

        printf("  Destination network: ");
        print_ip(cur->destnet);
        printf("\n");

        printf("  Netmask: ");
        print_ip(cur->netmask);
        printf("\n");

        printf("  Next hop IP: ");
        if (cur->nexthop == 0) {
            printf("(Direct)\n");
        }
        else {
            print_ip(cur->nexthop);
            printf("\n");
        }

        printf("--------------------------------------\n");
        cur = cur->next;
        idx++;
    }
}

// insert route (type=0: direct, placed before static; static sorted by netmask desc)
void rt_add(ROUTE_TABLE* rt, ULONG netmask, ULONG destnet, ULONG nexthop, int type) {
    ROUTE_ITEM* item = (ROUTE_ITEM*)malloc(sizeof(ROUTE_ITEM));
    if (!item) return;
    item->netmask = netmask;
    item->destnet = destnet;
    item->nexthop = nexthop;
    item->type = type;
    item->next = NULL;

    rt->count++;

    if (rt->head == NULL) {
        rt->head = item;
        return;
    }

    if (type == 0) {
        ROUTE_ITEM* prev = NULL;
        ROUTE_ITEM* cur = rt->head;
        while (cur && cur->type == 0) {
            prev = cur;
            cur = cur->next;
        }
        if (prev == NULL) {
            item->next = rt->head;
            rt->head = item;
        }
        else {
            item->next = cur;
            prev->next = item;
        }
        return;
    }

    ROUTE_ITEM* prev = NULL;
    ROUTE_ITEM* cur = rt->head;
    while (cur && (cur->type == 0 || cur->netmask > netmask)) {
        prev = cur;
        cur = cur->next;
    }
    if (prev == NULL) {
        item->next = rt->head;
        rt->head = item;
    }
    else {
        item->next = cur;
        prev->next = item;
    }
}

// delete by 0-based index
void rt_delete(ROUTE_TABLE* rt, int index0) {
    if (index0 < 0 || index0 >= rt->count) {
        printf("Route index %d out of range.\n", index0 + 1);
        return;
    }
    ROUTE_ITEM* prev = NULL;
    ROUTE_ITEM* cur = rt->head;
    int i = 0;
    while (cur && i < index0) {
        prev = cur;
        cur = cur->next;
        ++i;
    }
    if (!cur) return;
    if (cur->type == 0) {
        printf("Direct/default route cannot be deleted.\n");
        return;
    }
    if (prev == NULL) {
        rt->head = cur->next;
    }
    else {
        prev->next = cur->next;
    }
    free(cur);
    rt->count--;
}

// longest prefix match, return next hop IP (for direct, return dest_ip); fail -> 0xFFFFFFFF
ULONG rt_lookup(ROUTE_TABLE* rt, ULONG dest_ip) {
    ROUTE_ITEM* cur = rt->head;
    while (cur) {
        if ((dest_ip & cur->netmask) == cur->destnet) {
            if (cur->nexthop == 0) return dest_ip;
            else return cur->nexthop;
        }
        cur = cur->next;
    }
    return 0xFFFFFFFF;
}

// ======================= send ARP / IP =======================

void send_ip_with_mac(BYTE* packet, int len, const BYTE mac[6]) {
    ETH_HEADER* eth = (ETH_HEADER*)packet;
    int i;
    for (i = 0; i < 6; ++i) {
        eth->dest[i] = mac[i];
        eth->src[i] = g_my_mac[i];
    }
    eth->type = htons(0x0800);

    if (pcap_sendpacket(g_adhandle, packet, len) != 0) {
        printf("Send IP packet failed: %s\n", pcap_geterr(g_adhandle));
    }
    else {
        printf("Forward one packet, dest MAC: ");
        for (i = 0; i < 6; ++i) {
            printf("%02X", mac[i]);
            if (i < 5) printf("-");
        }
        printf("\n");
    }
}

void buffer_try_send_for_ip(ULONG ip, const BYTE mac[6]) {
    int i;
    for (i = 0; i < MAX_BUFFER; ++i) {
        if (g_buffer[i].used && g_buffer[i].dest_ip == ip) {
            send_ip_with_mac(g_buffer[i].data, g_buffer[i].len, mac);
            g_buffer[i].used = 0;
        }
    }
}

// send ARP request for target_ip
void send_arp_request(ULONG target_ip) {
    ARP_PACKET arp;
    int i;
    memset(&arp, 0, sizeof(arp));

    for (i = 0; i < 6; ++i) {
        arp.eth.dest[i] = 0xFF;
        arp.eth.src[i] = g_my_mac[i];
        arp.sha[i] = g_my_mac[i];
        arp.tha[i] = 0x00;
    }
    arp.eth.type = htons(0x0806);
    arp.htype = htons(1);
    arp.ptype = htons(0x0800);
    arp.hlen = 6;
    arp.plen = 4;
    arp.oper = htons(1);

    int idx = choose_if_for_ip(target_ip);
    arp.spa = g_my_ip[idx];
    arp.tpa = target_ip;

    if (pcap_sendpacket(g_adhandle, (const u_char*)&arp, sizeof(arp)) != 0) {
        printf("Send ARP request failed: %s\n", pcap_geterr(g_adhandle));
    }
    else {
        printf("Send ARP request to ");
        print_ip(target_ip);
        printf(" for MAC.\n");
    }
}

// ======================= handle ARP / IP =======================

void handle_arp(const u_char* packet, int len) {
    if (len < (int)sizeof(ARP_PACKET)) return;
    const ARP_PACKET* arp = (const ARP_PACKET*)packet;

    if (ntohs(arp->eth.type) != 0x0806) return;

    WORD op = ntohs(arp->oper);

    printf("\n=== ARP packet captured ===\n");
    printf("  Sender IP: ");
    print_ip(arp->spa);
    printf("  Target IP: ");
    print_ip(arp->tpa);
    printf("\n");

    if (op == 1) {
        printf("  ARP request.\n");
    }
    else if (op == 2) {
        int i;
        printf("  ARP reply.\n");
        printf("  Sender MAC: ");
        for (i = 0; i < 6; ++i) {
            printf("%02X", arp->sha[i]);
            if (i < 5) printf("-");
        }
        printf("\n");

        // update ARP table
        arp_add(arp->spa, arp->sha);

        // send buffered packets
        buffer_try_send_for_ip(arp->spa, arp->sha);
    }
}

// handle and forward IP packet
void handle_ip(const u_char* packet, int len, ROUTE_TABLE* rt) {
    if (len < (int)(sizeof(ETH_HEADER) + sizeof(IP_HEADER))) return;

    const ETH_HEADER* eth = (const ETH_HEADER*)packet;
    if (memcmp(eth->dest, g_my_mac, 6) != 0) {
        // only handle packets to this MAC
        return;
    }

    const IP_HEADER* ip = (const IP_HEADER*)(packet + sizeof(ETH_HEADER));
    int ihl = (ip->ver_ihl & 0x0F) * 4;

    printf("\n=== IP packet captured ===\n");
    printf("  Src IP: ");
    print_ip(ip->saddr);
    printf("\n  Dst IP: ");
    print_ip(ip->daddr);
    printf("\n  Original TTL: %d\n", ip->ttl);

    // checksum
    if (!ip_header_valid((IP_HEADER*)ip)) {
        printf("  IP header checksum error, drop.\n");
        return;
    }

    // local destination? do not forward
    int i;
    for (i = 0; i < g_ip_count; ++i) {
        if (ip->daddr == g_my_ip[i]) {
            printf("  Destination is local IP, not forwarded.\n");
            return;
        }
    }

    // TTL
    if (ip->ttl <= 1) {
        printf("  TTL too small, drop (could send ICMP Time Exceeded).\n");
        return;
    }

    // route lookup
    ULONG next_hop = rt_lookup(rt, ip->daddr);
    if (next_hop == 0xFFFFFFFF) {
        printf("  No route found, drop.\n");
        return;
    }

    printf("  Route lookup, next hop: ");
    print_ip(next_hop);
    if (next_hop == ip->daddr) {
        printf(" (direct delivery)\n");
    }
    else {
        printf(" (indirect delivery)\n");
    }

    // copy packet, decrement TTL and recalc checksum
    BYTE  sendbuf[2000];
    int   sendlen = len;
    if (sendlen > (int)sizeof(sendbuf)) sendlen = sizeof(sendbuf);
    memcpy(sendbuf, packet, sendlen);

    IP_HEADER* sip = (IP_HEADER*)(sendbuf + sizeof(ETH_HEADER));
    sip->ttl--;
    sip->check = 0;
    sip->check = ip_checksum((unsigned short*)sip, ihl);
    printf("  TTL before forwarding: %d\n", sip->ttl);

    BYTE dest_mac[6];
    ULONG mac_ip = next_hop;

    if (!arp_find(mac_ip, dest_mac)) {
        printf("  No MAC in ARP table, need ARP resolution.\n");
        buffer_add(sendbuf, sendlen, mac_ip);
        send_arp_request(mac_ip);
    }
    else {
        printf("  MAC found in ARP table, forward directly.\n");
        send_ip_with_mac(sendbuf, sendlen, dest_mac);
    }
}

// ======================= get local MAC (ARP trick) =======================

void get_my_mac() {
    ARP_PACKET arp;
    int i;
    memset(&arp, 0, sizeof(arp));

    for (i = 0; i < 6; ++i) {
        arp.eth.dest[i] = 0xFF;
        arp.eth.src[i] = 0x00;
        arp.sha[i] = 0x00;
        arp.tha[i] = 0x00;
    }
    arp.eth.type = htons(0x0806);
    arp.htype = htons(1);
    arp.ptype = htons(0x0800);
    arp.hlen = 6;
    arp.plen = 4;
    arp.oper = htons(1);

    // send ARP request to ourselves, wait OS reply
    arp.spa = g_my_ip[0];
    arp.tpa = g_my_ip[0];

    printf("Send ARP to get local MAC...\n");
    pcap_sendpacket(g_adhandle, (const u_char*)&arp, sizeof(arp));

    struct pcap_pkthdr* header;
    const u_char* pkt_data;
    int ret;

    while ((ret = pcap_next_ex(g_adhandle, &header, &pkt_data)) >= 0) {
        if (ret == 0) continue; // timeout

        if (header->len < (int)sizeof(ARP_PACKET)) continue;
        const ARP_PACKET* r = (const ARP_PACKET*)pkt_data;

        if (ntohs(r->eth.type) == 0x0806 &&
            ntohs(r->oper) == 2 &&
            r->spa == g_my_ip[0]) {
            for (i = 0; i < 6; ++i) g_my_mac[i] = r->sha[i];
            break;
        }
    }

    printf("Local MAC: ");
    for (i = 0; i < 6; ++i) {
        printf("%02X", g_my_mac[i]);
        if (i < 5) printf("-");
    }
    printf("\n");
}

// ======================= capture thread =======================

DWORD WINAPI recv_thread(LPVOID param) {
    ROUTE_TABLE* rt = (ROUTE_TABLE*)param;
    struct pcap_pkthdr* header;
    const u_char* pkt_data;

    while (1) {
        int ret = pcap_next_ex(g_adhandle, &header, &pkt_data);
        if (ret == 0) continue;   // timeout
        if (ret < 0)  break;      // error

        if (header->len < (int)sizeof(ETH_HEADER)) continue;
        const ETH_HEADER* eth = (const ETH_HEADER*)pkt_data;
        WORD type = ntohs(eth->type);

        if (type == 0x0806) {        // ARP
            handle_arp(pkt_data, header->len);
        }
        else if (type == 0x0800) {   // IP
            handle_ip(pkt_data, header->len, rt);
        }

        buffer_check_timeout();
    }
    return 0;
}

// ======================= main =======================

int main() {
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        printf("WSAStartup failed.\n");
        return 0;
    }

    char errbuf[PCAP_ERRBUF_SIZE];
    pcap_if_t* alldevs;
    pcap_if_t* d;
    int i, inum;

    if (pcap_findalldevs(&alldevs, errbuf) == -1) {
        printf("Error in pcap_findalldevs: %s\n", errbuf);
        return 0;
    }

    printf("Available adapters:\n");
    for (d = alldevs, i = 1; d != NULL; d = d->next, ++i) {
        printf("%d. %s", i, d->name);
        if (d->description) printf("  Desc: %s", d->description);
        printf("\n");

        pcap_addr_t* a;
        for (a = d->addresses; a != NULL; a = a->next) {
            if (a->addr && a->addr->sa_family == AF_INET) {
                struct sockaddr_in* sin_addr = (struct sockaddr_in*)a->addr;
                struct sockaddr_in* sin_mask = (struct sockaddr_in*)a->netmask;
                printf("    IP: %s   MASK: %s\n",
                    inet_ntoa(sin_addr->sin_addr),
                    inet_ntoa(sin_mask->sin_addr));
            }
        }
    }

    if (i == 1) {
        printf("No adapters found.\n");
        pcap_freealldevs(alldevs);
        return 0;
    }

    printf("Please select adapter index: ");
    scanf("%d", &inum);

    if (inum < 1 || inum >= i) {
        printf("Invalid adapter index.\n");
        pcap_freealldevs(alldevs);
        return 0;
    }

    // find the selected adapter
    for (d = alldevs, i = 1; i < inum; d = d->next, ++i);

    // get IP and mask of this adapter
    g_ip_count = 0;
    pcap_addr_t* a;
    printf("\nSelected adapter: %s\n", d->name);
    if (d->description) printf("Desc: %s\n", d->description);

    for (a = d->addresses; a != NULL && g_ip_count < 2; a = a->next) {
        if (a->addr && a->addr->sa_family == AF_INET) {
            struct sockaddr_in* sin_addr = (struct sockaddr_in*)a->addr;
            struct sockaddr_in* sin_mask = (struct sockaddr_in*)a->netmask;

            strcpy(g_my_ip_str[g_ip_count], inet_ntoa(sin_addr->sin_addr));
            strcpy(g_my_mask_str[g_ip_count], inet_ntoa(sin_mask->sin_addr));

            g_my_ip[g_ip_count] = sin_addr->sin_addr.S_un.S_addr;
            g_my_mask[g_ip_count] = sin_mask->sin_addr.S_un.S_addr;

            g_ip_count++;
        }
    }

    for (i = 0; i < g_ip_count; ++i) {
        printf("Local IP%d: %s  MASK: %s\n", i + 1, g_my_ip_str[i], g_my_mask_str[i]);
    }

    // open adapter
    g_adhandle = pcap_open_live(d->name, 65536, 1, 200, errbuf);
    if (g_adhandle == NULL) {
        printf("pcap_open_live failed: %s\n", errbuf);
        pcap_freealldevs(alldevs);
        return 0;
    }
    pcap_freealldevs(alldevs);

    arp_init();
    buffer_init();

    // get local MAC
    get_my_mac();

    // filter: only IP or ARP
    struct bpf_program fcode;
    if (pcap_compile(g_adhandle, &fcode, "ip or arp", 1, g_my_mask[0]) < 0) {
        fprintf(stderr, "pcap_compile failed.\n");
        return 0;
    }
    if (pcap_setfilter(g_adhandle, &fcode) < 0) {
        fprintf(stderr, "pcap_setfilter failed.\n");
        return 0;
    }

    // init route table: two direct routes
    ROUTE_TABLE rtable;
    rt_init(&rtable);
    if (g_ip_count >= 1) {
        rt_add(&rtable, g_my_mask[0], g_my_ip[0] & g_my_mask[0], 0, 0);
    }
    if (g_ip_count >= 2) {
        rt_add(&rtable, g_my_mask[1], g_my_ip[1] & g_my_mask[1], 0, 0);
    }

    printf("\nInitial route table:\n");
    rt_print(&rtable);

    // start capture thread
    DWORD tid;
    HANDLE hThread = CreateThread(NULL, 0, recv_thread, &rtable, 0, &tid);
    if (!hThread) {
        printf("CreateThread failed.\n");
        return 0;
    }

    // menu: add / delete / show routes
    while (1) {
        int op;
        printf("\n================== MENU ==================\n");
        printf(" 1. Add route\n");
        printf(" 2. Delete route\n");
        printf(" 3. Show route table\n");
        printf(" 4. Exit\n");
        printf("Input choice: ");
        scanf("%d", &op);

        if (op == 1) {
            char buf[32];
            ULONG netmask, destnet, nexthop;

            printf("Input netmask (e.g. 255.255.255.0):\n");
            scanf("%s", buf);
            netmask = inet_addr(buf);

            printf("Input destination network (e.g. 206.1.3.0):\n");
            scanf("%s", buf);
            destnet = inet_addr(buf);

            printf("Input next hop IP (e.g. 206.1.2.2):\n");
            scanf("%s", buf);
            nexthop = inet_addr(buf);

            rt_add(&rtable, netmask, destnet, nexthop, 1);
            printf("Add OK.\n");
        }
        else if (op == 2) {
            int index;
            printf("Input index to delete (start from 1):\n");
            scanf("%d", &index);
            rt_delete(&rtable, index - 1);
        }
        else if (op == 3) {
            rt_print(&rtable);
        }
        else if (op == 4) {
            printf("Exit program...\n");
            break;
        }
        else {
            printf("Invalid choice.\n");
        }
    }

    TerminateThread(hThread, 0);
    CloseHandle(hThread);
    pcap_close(g_adhandle);
    WSACleanup();
    return 0;
}

