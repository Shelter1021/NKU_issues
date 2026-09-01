#include <fstream>
#include <iostream>
#include "common.hpp"

int main() {
    default_r1cs_gg_ppzksnark_pp::init_public_params();

    protoboard<FieldT> pb;
    pb_variable<FieldT> x, x_sq, x_cu, out;

    // 构建约束系统（仅用于获取 primary_input 的布局）
    build_protoboard(pb, x, x_sq, x_cu, out);

    // 输入期望的公开输出 out
    long expected_out;
    cout << "Enter the expected 'out' value to verify: ";
    cin >> expected_out;
    pb.val(out) = expected_out;   // 只设置公开输入

    // 读取 verification key
    r1cs_gg_ppzksnark_verification_key<default_r1cs_gg_ppzksnark_pp> vk;
    ifstream vk_file("vk.raw", ios::binary);
    if (!vk_file) {
        cerr << "Failed to open vk.raw. Run setup first." << endl;
        return 1;
    }
    vk_file >> vk;
    vk_file.close();

    // 读取 proof
    r1cs_gg_ppzksnark_proof<default_r1cs_gg_ppzksnark_pp> proof;
    ifstream proof_file("proof.raw", ios::binary);
    if (!proof_file) {
        cerr << "Failed to open proof.raw. Run prove first." << endl;
        return 1;
    }
    proof_file >> proof;
    proof_file.close();

    // 验证
    bool result = r1cs_gg_ppzksnark_verifier_strong_IC<default_r1cs_gg_ppzksnark_pp>(
        vk, pb.primary_input(), proof);

    cout << "Verification result: " << (result ? "Pass!" : "Fail!") << endl;
    return 0;
}