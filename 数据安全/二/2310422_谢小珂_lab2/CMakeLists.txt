cmake_minimum_required(VERSION 3.10)
project(zk_experiment LANGUAGES CXX)

# libsnark 课程实验通常使用 C++14。
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 未显式指定构建类型时，默认使用 Release，避免证明生成过慢。
if (NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

find_package(OpenSSL REQUIRED)
find_package(Threads REQUIRED)
find_package(Boost QUIET COMPONENTS system filesystem)

# 兼容课程环境中手动安装到 /usr/local 的 libsnark / libff / libfqfft。
link_directories(/usr/local/lib)

add_executable(mysetup mysetup.cpp)
add_executable(myprove myprove.cpp)
add_executable(myverify myverify.cpp)

foreach(target mysetup myprove myverify)
    target_compile_definitions(${target} PRIVATE CURVE_ALT_BN128)

    target_include_directories(${target} PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
        /usr/local/include
        /usr/local/include/libsnark/depends
        /usr/local/include/libsnark/depends/libfqfft
        /usr/include
    )

    if (Boost_FOUND)
        target_include_directories(${target} PRIVATE ${Boost_INCLUDE_DIRS})
    endif()

    # 链接顺序不要随意调整：静态链接时，被依赖的库应放在依赖它们的库之后。
    target_link_libraries(${target} PRIVATE
        snark
        ff
        gmpxx
        gmp
        OpenSSL::Crypto
        Threads::Threads
    )

    if (Boost_FOUND)
        target_link_libraries(${target} PRIVATE ${Boost_LIBRARIES})
    endif()

    if (UNIX AND NOT APPLE)
        target_link_libraries(${target} PRIVATE dl)
    endif()
endforeach()

find_library(PROCPS_LIBRARY NAMES procps procps-ng)
if (PROCPS_LIBRARY)
    foreach(target mysetup myprove myverify)
        target_link_libraries(${target} PRIVATE ${PROCPS_LIBRARY})
    endforeach()
endif()
