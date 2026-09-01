#include "Node.h"

#include <iostream>

Node *root = nullptr;
long long start_update = -1;
long long end_update = -1;
std::map<std::string, long long> update;
long long leaf_split_count = 0;
long long internal_split_count = 0;

static long long max_code_bound() {
    return (1LL << 62);
}

static void recode(std::vector<LeafNode *> node_list) {
    if (node_list.empty()) return;

    long long left_bound = node_list.front()->lower;
    long long right_bound = node_list.back()->upper;

    int total_cipher_num = 0;
    for (LeafNode *node : node_list) {
        total_cipher_num += static_cast<int>(node->cipher.size());
    }
    if (total_cipher_num <= 0) return;

    if ((right_bound - left_bound) > total_cipher_num) {
        start_update = left_bound;
        end_update = right_bound;
        long long frag = static_cast<long long>(
            std::floor(static_cast<long double>(right_bound - left_bound) /
                       static_cast<long double>(total_cipher_num)));
        if (frag < 1) frag = 1;

        long long code = left_bound;
        update.clear();
        for (LeafNode *node : node_list) {
            node->lower = code;
            for (int j = 0; j < static_cast<int>(node->encoding.size()); ++j) {
                node->encoding[j] = code;
                update[node->cipher[j]] = code;
                code += frag;
            }
            node->upper = code;
        }
        node_list.back()->upper = right_bound;
        return;
    }

    bool expanded = false;
    if (node_list.front()->left_bro != nullptr) {
        node_list.insert(node_list.begin(), node_list.front()->left_bro);
        expanded = true;
    }
    if (node_list.back()->right_bro != nullptr) {
        node_list.push_back(node_list.back()->right_bro);
        expanded = true;
    }

    if (!expanded) {
        long long new_upper = node_list.back()->upper * 2;
        if (new_upper <= node_list.back()->upper) {
            new_upper = node_list.back()->upper + total_cipher_num + 2;
        }
        node_list.back()->upper = std::min(new_upper, max_code_bound());
    }

    recode(node_list);
}

InternalNode::InternalNode() {
    type = 2;
}

InternalNode::~InternalNode() {
    for (Node *n : child) {
        delete n;
    }
}

int InternalNode::count_items() const {
    int sum = 0;
    for (int n : child_num) sum += n;
    return sum;
}

void InternalNode::recompute_child_num() {
    for (int i = 0; i < static_cast<int>(child.size()); ++i) {
        child[i]->parent = this;
        child[i]->parent_index = i;
        child_num[i] = child[i]->count_items();
    }
}

void InternalNode::insert_node(int index, Node *new_node) {
    if (index < 0) index = 0;
    if (index > static_cast<int>(child.size())) index = static_cast<int>(child.size());

    child.insert(child.begin() + index, new_node);
    child_num.insert(child_num.begin() + index, new_node->count_items());
    recompute_child_num();

    if (static_cast<int>(child.size()) >= FHOPE_M) {
        rebalance();
    }
}

void InternalNode::rebalance() {
    internal_split_count++;

    auto *new_node = new InternalNode();
    int move_count = static_cast<int>(std::floor(child.size() * 0.5));

    while (move_count > 0) {
        new_node->child.insert(new_node->child.begin(), child.back());
        new_node->child_num.insert(new_node->child_num.begin(), child_num.back());
        child.pop_back();
        child_num.pop_back();
        --move_count;
    }

    recompute_child_num();
    new_node->recompute_child_num();

    if (parent == nullptr) {
        auto *new_root = new InternalNode();
        new_root->insert_node(0, this);
        new_root->insert_node(1, new_node);
        root = new_root;
    } else {
        auto *p = static_cast<InternalNode *>(parent);
        p->child_num[parent_index] = count_items();
        p->insert_node(parent_index + 1, new_node);
    }
}

long long InternalNode::insert(int pos, const std::string &ciphertext) {
    if (child.empty()) return 0;

    if (pos < 0) pos = 0;
    int total = count_items();
    if (pos > total) pos = total;

    for (int i = 0; i < static_cast<int>(child.size()); ++i) {
        if (pos <= child_num[i]) {
            child_num[i]++;
            return child[i]->insert(pos, ciphertext);
        }
        pos -= child_num[i];
    }

    child_num.back()++;
    return child.back()->insert(child.back()->count_items(), ciphertext);
}

long long InternalNode::search(int pos) {
    if (child.empty()) return 0;
    if (pos < 0) pos = 0;

    for (int i = 0; i < static_cast<int>(child.size()); ++i) {
        if (pos < child_num[i]) {
            return child[i]->search(pos);
        }
        pos -= child_num[i];
    }

    return child.back()->search(child.back()->count_items() - 1);
}

LeafNode::LeafNode() {
    type = 1;
}

int LeafNode::count_items() const {
    return static_cast<int>(cipher.size());
}

long long LeafNode::encode(int pos) {
    long long left = lower;
    long long right = upper;

    if (pos > 0) {
        left = encoding[pos - 1];
    }
    if (pos < static_cast<int>(encoding.size()) - 1) {
        right = encoding[pos + 1];
    }

    if ((right - left) < 2) {
        std::vector<LeafNode *> node_list;
        node_list.push_back(this);
        recode(node_list);
        return 0;  // SQL procedure will call FHUpdate to sync old rows and the new row.
    }

    long long frag = (right - left) / 2;
    encoding[pos] = right - frag;
    return encoding[pos];
}

void LeafNode::rebalance() {
    leaf_split_count++;

    auto *new_node = new LeafNode();
    int move_count = static_cast<int>(std::floor(cipher.size() * 0.5));

    while (move_count > 0) {
        new_node->cipher.insert(new_node->cipher.begin(), cipher.back());
        new_node->encoding.insert(new_node->encoding.begin(), encoding.back());
        cipher.pop_back();
        encoding.pop_back();
        --move_count;
    }

    new_node->lower = new_node->encoding.front();
    new_node->upper = upper;
    upper = new_node->encoding.front();

    if (right_bro != nullptr) {
        right_bro->left_bro = new_node;
    }
    new_node->right_bro = right_bro;
    right_bro = new_node;
    new_node->left_bro = this;

    if (parent == nullptr) {
        auto *new_root = new InternalNode();
        new_root->insert_node(0, this);
        new_root->insert_node(1, new_node);
        root = new_root;
    } else {
        auto *p = static_cast<InternalNode *>(parent);
        p->child_num[parent_index] = count_items();
        p->insert_node(parent_index + 1, new_node);
    }
}

long long LeafNode::insert(int pos, const std::string &ciphertext) {
    if (pos < 0) pos = 0;
    if (pos > static_cast<int>(cipher.size())) {
        pos = static_cast<int>(cipher.size());
    }

    cipher.insert(cipher.begin() + pos, ciphertext);
    encoding.insert(encoding.begin() + pos, -1);

    long long code = encode(pos);

    if (static_cast<int>(cipher.size()) >= FHOPE_M) {
        rebalance();
    }
    return code;
}

long long LeafNode::search(int pos) {
    if (cipher.empty()) return 0;
    if (pos < 0) pos = 0;
    if (pos >= static_cast<int>(encoding.size())) {
        pos = static_cast<int>(encoding.size()) - 1;
    }
    return encoding[pos];
}

void root_initial() {
    if (root != nullptr) {
        delete root;
    }
    root = new LeafNode();
    static_cast<LeafNode *>(root)->lower = 0;
    static_cast<LeafNode *>(root)->upper = FHOPE_INITIAL_UPPER;
    start_update = -1;
    end_update = -1;
    update.clear();
}

void reset_all() {
    if (root != nullptr) {
        delete root;
        root = nullptr;
    }
    leaf_split_count = 0;
    internal_split_count = 0;
    root_initial();
}

long long get_update(const std::string &ciphertext) {
    auto it = update.find(ciphertext);
    if (it == update.end()) return 0;
    return it->second;
}

int total_items() {
    if (root == nullptr) return 0;
    return root->count_items();
}
