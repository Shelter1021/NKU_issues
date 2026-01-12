// chatroom_client.cpp
// 简易聊天室客户端：连接 127.0.0.1:9090，不 bind（全中文提示 + 本地回显加时间戳）
#define _WINSOCK_DEPRECATED_NO_WARNINGS
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iostream>
#include <string>
#include <thread>
#include <chrono>
#include <ctime>
#include <iomanip>
#include <sstream>

#pragma comment(lib, "ws2_32.lib")

const char* SERVER_IP = "127.0.0.1";
const int   SERVER_PORT = 9090;

SOCKET g_sock = INVALID_SOCKET;
bool   g_running = true;

// "YYYY-MM-DD HH:MM:SS"
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

// 接收线程：打印服务器广播/别人说的话（服务器已带上时间戳）
void recv_thread() {
    char buf[512];
    while (g_running) {
        int r = recv(g_sock, buf, sizeof(buf) - 1, 0);
        if (r <= 0) {
            std::cout << "\n[系统] 与服务器的连接已断开。\n";
            g_running = false;
            break;
        }
        buf[r] = 0;
        std::cout << buf;   // 服务器消息里已是中文 & 带时间戳
    }
}

// 用 WinAPI 把控制台的“上一行”清空（为了只显示 [我] 这一行）
void clear_prev_line() {
    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    CONSOLE_SCREEN_BUFFER_INFO csbi;
    if (!GetConsoleScreenBufferInfo(hOut, &csbi)) return;
    if (csbi.dwCursorPosition.Y == 0) return;

    SHORT width = csbi.dwSize.X;
    COORD lineStart{ 0, (SHORT)(csbi.dwCursorPosition.Y - 1) };
    SetConsoleCursorPosition(hOut, lineStart);
    DWORD written;
    FillConsoleOutputCharacterA(hOut, ' ', width, lineStart, &written);
    FillConsoleOutputAttribute(hOut, csbi.wAttributes, width, lineStart, &written);
    SetConsoleCursorPosition(hOut, lineStart);
}

int main() {
    // 使用系统默认编码
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) { std::cout << "初始化网络库失败。\n"; return 1; }

    g_sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (g_sock == INVALID_SOCKET) { std::cout << "套接字创建失败。\n"; WSACleanup(); return 1; }

    sockaddr_in srv{};
    srv.sin_family = AF_INET;
    srv.sin_port = htons(SERVER_PORT);
    inet_pton(AF_INET, SERVER_IP, &srv.sin_addr);

    if (connect(g_sock, (sockaddr*)&srv, sizeof(srv)) == SOCKET_ERROR) {
        std::cout << "连接失败，请确认服务器已启动。\n";
        closesocket(g_sock); WSACleanup(); return 1;
    }

    std::cout << "已连接到服务器，请输入您的用户名：";
    std::string name;
    std::getline(std::cin, name);
    if (name.empty()) name = "guest";

    // 把名字告诉服务器
    send(g_sock, name.c_str(), (int)name.size(), 0);

    // 登录成功提示（本地）
    std::cout << "您已成功进入聊天室，现在开始聊天吧~\n";
    std::cout << "请输入聊天内容，输入 quit 退出。\n";

    // 开收线程
    std::thread t(recv_thread);

    // 主线程发
    while (g_running) {
        std::string line;
        if (!std::getline(std::cin, line)) break;

        if (line == "quit") {
            g_running = false;
            break;
        }

        // 覆盖上一行原始输入，只保留我们格式化后的输出
        clear_prev_line();

        // 本地回显：[我] 内容 [时间戳]
        std::cout << "[我] " << line << " [" << now_str() << "]\n";

        // 发给服务器（让其他人看到 [名字] 内容 [时间戳]）
        std::string sendline = line + "\n";
        send(g_sock, sendline.c_str(), (int)sendline.size(), 0);
    }

    closesocket(g_sock);
    g_running = false;
    t.join();
    WSACleanup();
    return 0;
}

