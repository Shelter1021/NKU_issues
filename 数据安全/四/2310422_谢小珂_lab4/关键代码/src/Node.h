#pragma once

#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

#ifndef FHOPE_M
#define FHOPE_M 4
#endif

#ifndef FHOPE_INITIAL_UPPER
#define FHOPE_INITIAL_UPPER (1LL << 8)
#endif

class Node {
public:
    int type = 0;             // 1 = LeafNode, 2 = InternalNode
    int parent_index = -1;    // index in parent->child
    Node *parent = nullptr;

    virtual ~Node() = default;
    virtual void rebalance() {}
    virtual long long insert(int pos, const std::string &cipher) { return 0; }
    virtual long long search(int pos) { return 0; }
    virtual int count_items() const { return 0; }
};

class InternalNode : public Node {
public:
    std::vector<int> child_num;
    std::vector<Node *> child;

    InternalNode();
    ~InternalNode() override;

    void insert_node(int index, Node *new_node);
    void recompute_child_num();
    void rebalance() override;
    long long insert(int pos, const std::string &cipher) override;
    long long search(int pos) override;
    int count_items() const override;
};

class LeafNode : public Node {
public:
    std::vector<std::string> cipher;
    std::vector<long long> encoding;
    LeafNode *left_bro = nullptr;
    LeafNode *right_bro = nullptr;
    long long lower = -1;
    long long upper = -1;

    LeafNode();

    long long encode(int pos);
    void rebalance() override;
    long long insert(int pos, const std::string &cipher) override;
    long long search(int pos) override;
    int count_items() const override;
};

extern Node *root;
extern long long start_update;
extern long long end_update;
extern std::map<std::string, long long> update;
extern long long leaf_split_count;
extern long long internal_split_count;

void root_initial();
void reset_all();
long long get_update(const std::string &cipher);
int total_items();
