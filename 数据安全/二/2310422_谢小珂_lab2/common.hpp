#ifndef COMMON_HPP
#define COMMON_HPP

#include <libsnark/common/default_types/r1cs_gg_ppzksnark_pp.hpp>
#include <libsnark/zk_proof_systems/ppzksnark/r1cs_gg_ppzksnark/r1cs_gg_ppzksnark.hpp>
#include <libsnark/gadgetlib1/pb_variable.hpp>

using namespace libsnark;
using namespace std;

typedef libff::Fr<default_r1cs_gg_ppzksnark_pp> FieldT;

// 构建 R1CS 约束：x * x = x_sq, x_sq * x = x_cu, 1*(x_cu + x + 5) = out
// 公开输入只有 out，中间变量 x_sq 和 x_cu 为私有 witness
void build_protoboard(protoboard<FieldT> &pb,
                      pb_variable<FieldT> &x,
                      pb_variable<FieldT> &x_sq,
                      pb_variable<FieldT> &x_cu,
                      pb_variable<FieldT> &out)
{
    // 分配所有变量（顺序与约束系统稳定性相关，但不影响正确性）
    out.allocate(pb, "out");
    x.allocate(pb, "x");
    x_sq.allocate(pb, "x_sq");
    x_cu.allocate(pb, "x_cu");

    // 定义常量 5
    pb_variable<FieldT> const_5;
    const_5.allocate(pb, "const_5");
    pb.val(const_5) = FieldT(5);

    // 设置公开输入个数（只有 out 是公开的）
    pb.set_input_sizes(1);

    // 添加约束
    // 1. x * x = x_sq
    pb.add_r1cs_constraint(r1cs_constraint<FieldT>(x, x, x_sq));
    // 2. x_sq * x = x_cu
    pb.add_r1cs_constraint(r1cs_constraint<FieldT>(x_sq, x, x_cu));
    // 3. x_cu + x + 5 = out   ->   1 * (x_cu + x + 5) = out
    pb.add_r1cs_constraint(r1cs_constraint<FieldT>(1, x_cu + x + const_5, out));
}

#endif // COMMON_HPP