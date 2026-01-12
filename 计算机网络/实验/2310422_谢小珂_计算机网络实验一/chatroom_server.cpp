// chatroom_server.cpp
// 多线程转发，端口 9090（全中文提示；为每条消息末尾追加时间戳）
#define _WINSOCK_DEPRECATED_NO_WARNINGS
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iostream>
#include <string>
#include <thread>
#include <vector>
#include <mutex>
#include <chrono>
#include <ctime>
#include <iomanip>
#include <sstream>

#pragma comment(lib, "ws2_32.lib")

const int SERVER_PORT = 9090;

struct Client {
    SOCKET s;
    std::string name;
};

std::vector<Client> g_clients;
std::mutex g_mtx;

// 生成 "YYYY-MM-DD HH:MM:SS"
static std::string now_str() {
    using namespace std::chrono;
    auto now = system_clock::now();
    std::time_t t = system_clock::to_time_t(now);
    std::tm tm{};
    localtime_s(&tm, &t);
    std::ostringstream oss;
    oss << std::put_time(&tm, "%Y-%m-%d %H:%M:%S");
    return oss.str();
}

void broadcast(const std::string& msg, SOCKET except = INVALID_SOCKET) {
    std::lock_guard<std::mutex> lk(g_mtx);
    for (auto& c : g_clients) {
        if (c.s == except) continue;
        send(c.s, msg.c_str(), (int)msg.size(), 0);
    }
}

void client_thread(SOCKET cli) {
    // 1) 首包昵称
    char namebuf[128] = { 0 };
    int n = recv(cli, namebuf, sizeof(namebuf) - 1, 0);
    std::string uname = n > 0 ? std::string(namebuf, n) : "guest";

    {
        std::lock_guard<std::mutex> lk(g_mtx);
        g_clients.push_back({ cli, uname });
    }

    // 2) 给“本人”回一条：已成功建立连接（带时间）
    {
        std::string ok = "[系统] " + uname + " 已成功建立连接。[" + now_str() + "]\n";
        send(cli, ok.c_str(), (int)ok.size(), 0);
    }

    // 3) 广播加入（给其他人看，带时间）
    {
        std::string joinMsg = "[系统] " + uname + " 加入了聊天室。[" + now_str() + "]\n";
        broadcast(joinMsg, cli);
    }

    // 4) 循环收聊天
    char buf[1024];
    while (true) {
        int r = recv(cli, buf, sizeof(buf) - 1, 0);
        if (r <= 0) break;
        buf[r] = 0;

        // 去掉结尾的 \r 或 \n，避免时间戳被换行分开
        std::string text(buf);
        while (!text.empty() && (text.back() == '\n' || text.back() == '\r')) {
            text.pop_back();
        }

        // 统一格式：[名字] 内容 [时间戳]\n
        std::string line = "[" + uname + "] " + text + " [" + now_str() + "]\n";
        broadcast(line, cli);
    }

    // 5) 下线清理 + 离开广播（带时间）
    {
        std::lock_guard<std::mutex> lk(g_mtx);
        for (auto it = g_clients.begin(); it != g_clients.end(); ++it) {
            if (it->s == cli) { g_clients.erase(it); break; }
        }
    }
    {
        std::string leaveMsg = "[系统] " + uname + " 离开了聊天室。[" + now_str() + "]\n";
        broadcast(leaveMsg, cli);
    }

    closesocket(cli);
}

int main() {
    // 使用系统默认编码以避免控制台乱码
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        std::cout << "初始化网络库失败。\n";
        return 1;
    }

    SOCKET srv = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (srv == INVALID_SOCKET) {
        std::cout << "套接字创建失败。\n";
        WSACleanup();
        return 1;
    }

    int opt = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, (char*)&opt, sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(SERVER_PORT);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);

    if (bind(srv, (sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR) {
        std::cout << "绑定失败（端口 " << SERVER_PORT << "）。\n";
        closesocket(srv); WSACleanup(); return 1;
    }
    if (listen(srv, SOMAXCONN) == SOCKET_ERROR) {
        std::cout << "监听失败。\n";
        closesocket(srv); WSACleanup(); return 1;
    }

    // ✅ 启动提示（中文）
    std::cout << "服务器已启动，端口是 " << SERVER_PORT << "，等待客户端的连接……\n";

    while (true) {
        sockaddr_in caddr{}; int clen = sizeof(caddr);
        SOCKET cli = accept(srv, (sockaddr*)&caddr, &clen);
        if (cli == INVALID_SOCKET) continue;
        std::thread t(client_thread, cli);
        t.detach();
    }

    closesocket(srv);
    WSACleanup();
    return 0;
}
