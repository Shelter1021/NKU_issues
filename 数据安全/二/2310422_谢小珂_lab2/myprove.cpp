#include <fstream>
#include <iostream>
#include <cstdlib>
#include "common.hpp"

int main(int argc, char *argv[]) {
    if (argc != 2) {
        cerr << "Usage: " << argv[0] << " <x>" << endl;
        return 1;
    }
    long x_val = atol(argv[1]);

    default_r1cs_gg_ppzksnark_pp::init_public_params();

    protoboard<FieldT> pb;
    pb_variable<FieldT> x, x_sq, x_cu, out;

    build_protoboard(pb, x, x_sq, x_cu, out);

    // 赋值 witness
    pb.val(x) = x_val;
    pb.val(x_sq) = x_val * x_val;
    pb.val(x_cu) = x_val * x_val * x_val;
    pb.val(out) = pb.val(x_cu) + pb.val(x) + 5;

    // 检查约束是否满足
    if (!pb.is_satisfied()) {
        cerr << "Constraint system not satisfied! Please check assignment." << endl;
        return 1;
    }

    // 读取 proving key
    r1cs_gg_ppzksnark_proving_key<default_r1cs_gg_ppzksnark_pp> pk;
    ifstream pk_file("pk.raw", ios::binary);
    if (!pk_file) {
        cerr << "Failed to open pk.raw. Run setup first." << endl;
        return 1;
    }
    pk_file >> pk;
    pk_file.close();

    // 生成证明
    auto proof = r1cs_gg_ppzksnark_prover<default_r1cs_gg_ppzksnark_pp>(
        pk, pb.primary_input(), pb.auxiliary_input());

    // 保存证明
    ofstream proof_file("proof.raw", ios::binary);
    proof_file << proof;
    proof_file.close();

    cout << "Prove finished. out = " << pb.val(out) << endl;
    return 0;
}