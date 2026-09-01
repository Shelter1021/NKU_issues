#include <fstream>
#include <iostream>
#include "common.hpp"

int main() {
    default_r1cs_gg_ppzksnark_pp::init_public_params();

    protoboard<FieldT> pb;
    pb_variable<FieldT> x, x_sq, x_cu, out;

    // 构建同样的约束系统，但不赋值具体数值
    build_protoboard(pb, x, x_sq, x_cu, out);

    const r1cs_constraint_system<FieldT> constraint_system = pb.get_constraint_system();

    // 生成密钥对
    auto keypair = r1cs_gg_ppzksnark_generator<default_r1cs_gg_ppzksnark_pp>(constraint_system);

    // 保存 proving key 和 verification key
    ofstream pk_file("pk.raw", ios::binary);
    pk_file << keypair.pk;
    pk_file.close();

    ofstream vk_file("vk.raw", ios::binary);
    vk_file << keypair.vk;
    vk_file.close();

    cout << "Setup finished. pk.raw and vk.raw generated." << endl;
    return 0;
}