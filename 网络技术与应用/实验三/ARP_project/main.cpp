#include <pcap.h>
#include <stdio.h>

int main() {
    pcap_if_t *alldevs;
    char errbuf[PCAP_ERRBUF_SIZE];

    if (pcap_findalldevs(&alldevs, errbuf) == -1) {
        printf("NPcap not found: %s\n", errbuf);
        return -1;
    }

    printf(" NPcap is working! Devices detected.\n");
    return 0;
}
